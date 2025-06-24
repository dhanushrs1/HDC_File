#(©)CodeXBotz

import pymongo, os
from config import DB_URI, DB_NAME
from datetime import datetime, timedelta

dbclient = pymongo.MongoClient(DB_URI)
database = dbclient[DB_NAME]
user_data = database['users']
analytics_data = database['analytics']
file_index = database['file_index'] # New collection for search

# Create a text index for efficient searching on the file_name field
if "file_name_text" not in file_index.index_information():
    file_index.create_index([("file_name", pymongo.TEXT)], name="file_name_text")


# --- User Management Functions ---
async def add_user(user_id: int):
    user = await get_user(user_id)
    if user and user.get('banned', False):
        return await unban_user(user_id)
    elif not user:
        user_data.insert_one({'_id': user_id, 'banned': False})

async def get_user(user_id: int):
    return user_data.find_one({'_id': user_id})

async def present_user(user_id : int):
    found = await get_user(user_id)
    return bool(found) and not found.get('banned', False)

async def full_userbase():
    cursor = user_data.find({'banned': {'$ne': True}})
    return [user['_id'] for user in cursor]

async def get_all_users_data():
    return list(user_data.find())
    
async def del_user(user_id: int):
    user_data.delete_one({'_id': user_id})

async def ban_user(user_id: int):
    user_data.update_one({'_id': user_id}, {'$set': {'banned': True}}, upsert=True)

async def unban_user(user_id: int):
    user_data.update_one({'_id': user_id}, {'$set': {'banned': False}}, upsert=True)

# --- Analytics Functions ---
async def log_file_download(file_id: int, user_id: int):
    analytics_data.insert_one({'file_id': file_id, 'user_id': user_id, 'timestamp': datetime.now()})

async def get_daily_download_counts():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    pipeline = [{'$facet': {'today': [{'$match': {'timestamp': {'$gte': today}}}, {'$count': 'count'}], 'yesterday': [{'$match': {'timestamp': {'$gte': yesterday, '$lt': today}}}, {'$count': 'count'}], 'day_before': [{'$match': {'timestamp': {'$gte': day_before, '$lt': yesterday}}}, {'$count': 'count'}]}}]
    result = list(analytics_data.aggregate(pipeline))[0]
    today_count = result['today'][0]['count'] if result['today'] else 0
    yesterday_count = result['yesterday'][0]['count'] if result['yesterday'] else 0
    day_before_count = result['day_before'][0]['count'] if result['day_before'] else 0
    return today_count, yesterday_count, day_before_count

async def get_top_downloaded_files(limit=10):
    pipeline = [{'$group': {'_id': '$file_id', 'count': {'$sum': 1}}}, {'$sort': {'count': -1}}, {'$limit': limit}]
    return list(analytics_data.aggregate(pipeline))

# --- New, Smarter Search Index Functions ---

async def add_to_search_index(message):
    """Adds a file's metadata to the search index and returns its status."""
    file_id = message.id
    file_name = None
    file_size = 0
    duration = 0
    date_added = message.date

    if message.document:
        file_name = message.document.file_name
        file_size = message.document.file_size
    elif message.video:
        file_name = message.video.file_name
        file_size = message.video.file_size
        duration = message.video.duration or 0

    if not file_name:
        return "no_filename"

    result = file_index.update_one(
        {'_id': file_id},
        {'$set': {
            'file_name': file_name,
            'file_size': file_size,
            'date_added': date_added,
            'duration': duration
        }},
        upsert=True
    )
    
    if result.upserted_id is not None:
        return "new" # A new file was added
    else:
        return "duplicate" # An existing file was updated

async def search_indexed_files(query, limit=15):
    """Searches for files in the local index."""
    results = file_index.find(
        {'$text': {'$search': query}},
        {'score': {'$meta': 'textScore'}}
    ).sort([('score', {'$meta': 'textScore'})]).limit(limit)
    
    return list(results)

async def count_indexed_files():
    """Counts the total number of files in the index."""
    return file_index.count_documents({})