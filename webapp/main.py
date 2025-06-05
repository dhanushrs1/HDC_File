import datetime
from functools import wraps
from flask import Flask, request, redirect, render_template_string, session, url_for, abort, make_response
from pymongo import MongoClient, DESCENDING, ASCENDING

# Import configuration from the root directory
import sys
sys.path.append('..') # Adds the parent directory to the Python path
import config

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# Initialize MongoDB Client
mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB_NAME]
files_collection = db["files"]
access_logs_collection = db["access_logs"]

# Ensure indexes for MongoDB (though bot might create them, good to have here too)
if "access_logs" not in db.list_collection_names(): # Create if not exists
    access_logs_collection.create_index("file_id")
    access_logs_collection.create_index([("access_timestamp", DESCENDING)])


# --- Authentication for Admin ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == config.FLASK_ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True  # Make session last longer
            app.permanent_session_lifetime = datetime.timedelta(days=7)
            next_url = request.args.get('next')
            return redirect(next_url or url_for('admin_dashboard'))
        else:
            error = 'Invalid Password. Please try again.'
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# --- File Access Route ---
@app.route('/file/<file_id_str>')
def access_file(file_id_str):
    file_record = files_collection.find_one({"file_id": file_id_str})

    if not file_record:
        abort(404, description="File not found.")

    # Log access
    try:
        access_log_entry = {
            "file_id": file_id_str,
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get('User-Agent'),
            "access_timestamp": datetime.datetime.utcnow()
        }
        access_logs_collection.insert_one(access_log_entry)

        # Increment view count
        files_collection.update_one(
            {"file_id": file_id_str},
            {"$inc": {"view_count": 1}}
        )
    except Exception as e:
        app.logger.error(f"Error logging access or incrementing view count for {file_id_str}: {e}")


    storage_channel_id_for_link = config.get_telegram_link_channel_id(file_record['storage_channel_id'])
    message_id = file_record['message_id_in_storage']
    
    # Construct the direct Telegram message link
    # Format: https://t.me/c/<channel_numeric_id>/<message_id>
    telegram_link = f"https://t.me/c/{storage_channel_id_for_link}/{message_id}"
    
    # Redirect to the Telegram message
    return redirect(telegram_link, code=302)

# --- Admin Dashboard Route ---
@app.route('/admin')
@login_required
def admin_dashboard():
    total_files = files_collection.count_documents({})
    
    top_downloaded_files = list(files_collection.find({"view_count": {"$gt": 0}})
                                .sort("view_count", DESCENDING)
                                .limit(10))
    
    # Files by user: {user_id: {'name': 'name', 'count': count}}
    # This pipeline groups by user_id and gets the first name and count
    pipeline = [
        {"$group": {
            "_id": "$uploaded_by_user_id",
            "count": {"$sum": 1},
            "user_firstname": {"$first": "$uploaded_by_user_firstname"} # Assumes firstname is stored
        }},
        {"$sort": {"count": DESCENDING}},
        {"$limit": 10}
    ]
    files_by_user_agg = list(files_collection.aggregate(pipeline))
    
    files_by_user = [
        {"user_id": item["_id"], 
         "user_firstname": item.get("user_firstname", "N/A"), 
         "count": item["count"]}
        for item in files_by_user_agg
    ]

    recent_accesses_raw = list(access_logs_collection.find().sort("access_timestamp", DESCENDING).limit(20))
    
    # Enrich recent accesses with file names
    recent_accesses = []
    for log in recent_accesses_raw:
        file_info = files_collection.find_one({"file_id": log["file_id"]}, {"original_file_name": 1})
        log["original_file_name"] = file_info["original_file_name"] if file_info else "N/A (deleted?)"
        recent_accesses.append(log)

    return render_template_string(
        ADMIN_DASHBOARD_TEMPLATE,
        total_files=total_files,
        top_downloaded_files=top_downloaded_files,
        files_by_user=files_by_user,
        recent_accesses=recent_accesses
    )

@app.errorhandler(404)
def page_not_found(e):
    return render_template_string("<h1>404 - Not Found</h1><p>{{ description }}</p>", description=e.description), 404

# --- HTML Templates (embedded for simplicity) ---

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login</title>
    <style>
        body { font-family: sans-serif; margin: 0; background-color: #f4f4f4; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .login-container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); width: 300px; }
        h2 { text-align: center; color: #333; }
        label { display: block; margin-bottom: 5px; color: #555; }
        input[type="password"] { width: calc(100% - 22px); padding: 10px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 4px; }
        input[type="submit"] { background-color: #007bff; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
        input[type="submit"]:hover { background-color: #0056b3; }
        .error { color: red; text-align: center; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Admin Login</h2>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
        <form method="post">
            <label for="password">Password:</label>
            <input type="password" id="password" name="password" required>
            <input type="submit" value="Login">
        </form>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f9f9f9; color: #333; }
        h1, h2 { color: #0056b3; }
        .container { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background-color: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
        .card h2 { margin-top: 0; font-size: 1.2em; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #eee; }
        th { background-color: #f0f0f0; }
        tr:hover { background-color: #f5f5f5; }
        .logout-link { position: absolute; top: 20px; right: 20px; text-decoration: none; background-color: #d9534f; color: white; padding: 8px 12px; border-radius: 4px; }
        .logout-link:hover { background-color: #c9302c; }
        .timestamp { font-size: 0.9em; color: #777; }
        .user-agent { font-size: 0.8em; color: #888; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>
    <a href="{{ url_for('logout') }}" class="logout-link">Logout</a>
    <h1>Admin Dashboard</h1>

    <div class="card">
        <h2>Overall Stats</h2>
        <p>Total Files Uploaded: <strong>{{ total_files }}</strong></p>
    </div>

    <div class="container">
        <div class="card">
            <h2>Top Downloaded Files (Top 10)</h2>
            {% if top_downloaded_files %}
                <table>
                    <thead><tr><th>File Name</th><th>File ID</th><th>Views</th></tr></thead>
                    <tbody>
                    {% for file in top_downloaded_files %}
                        <tr>
                            <td>{{ file.original_file_name }}</td>
                            <td><a href="{{ url_for('access_file', file_id_str=file.file_id) }}" target="_blank">{{ file.file_id }}</a></td>
                            <td>{{ file.view_count }}</td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <p>No files have been viewed yet.</p>
            {% endif %}
        </div>

        <div class="card">
            <h2>Files by User (Top 10 Uploaders)</h2>
             {% if files_by_user %}
                <table>
                    <thead><tr><th>User First Name</th><th>User ID</th><th>Files Uploaded</th></tr></thead>
                    <tbody>
                    {% for user_stat in files_by_user %}
                        <tr>
                            <td>{{ user_stat.user_firstname }}</td>
                            <td>{{ user_stat.user_id }}</td>
                            <td>{{ user_stat.count }}</td>
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <p>No files uploaded yet.</p>
            {% endif %}
        </div>
    </div>
    
    <div class="card" style="margin-top: 20px;">
        <h2>Recent Download History (Last 20)</h2>
        {% if recent_accesses %}
            <table>
                <thead><tr><th>File Name</th><th>File ID</th><th>IP Address</th><th>User Agent</th><th>Timestamp (UTC)</th></tr></thead>
                <tbody>
                {% for log in recent_accesses %}
                    <tr>
                        <td>{{ log.original_file_name }}</td>
                        <td><a href="{{ url_for('access_file', file_id_str=log.file_id) }}" target="_blank">{{ log.file_id }}</a></td>
                        <td>{{ log.ip_address }}</td>
                        <td class="user-agent" title="{{ log.user_agent }}">{{ log.user_agent }}</td>
                        <td class="timestamp">{{ log.access_timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p>No download activity yet.</p>
        {% endif %}
    </div>

</body>
</html>
"""

if __name__ == "__main__":
    # For local development only. Use Gunicorn in production.
    app.run(host="0.0.0.0", port=5000, debug=True)