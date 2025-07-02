"""
(©) HD Cinema Bot

This file manages all interactions with the MongoDB database.
- Establishes a connection to the database.
- Manages collections for users, analytics, and the file search index.
- Provides async functions for all CRUD (Create, Read, Update, Delete) operations.
"""

import logging
import sys
from datetime import datetime, timezone, timedelta
import pymongo
from pymongo.errors import ConnectionFailure, OperationFailure

# Import configuration
from config import DB_URI, DB_NAME

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Database Connection and Setup ---
try:
    dbclient = pymongo.MongoClient(DB_URI)
    database = dbclient[DB_NAME]
    
    # --- Collections ---
    user_data = database['users']
    analytics_data = database['analytics']
    file_index = database['file_index']
    approved_groups = database['groups'] # Collection for approved groups

    # --- Create Indexes for Performance ---
    if "file_name_text" not in file_index.index_information():
        file_index.create_index([("file_name", pymongo.TEXT)], name="file_name_text", default_language="english")
        logger.info("Created text index on 'file_index' collection.")

    if "_id_" not in user_data.index_information():
        user_data.create_index([("_id", pymongo.ASCENDING)], name="_id_")
        logger.info("Ensured default index on 'users' collection's _id field.")

    logger.info(f"Successfully connected to MongoDB database: {DB_NAME}")

except ConnectionFailure as e:
    logger.critical(f"FATAL: Could not connect to MongoDB. Please check your DB_URI. Error: {e}")
    sys.exit(1)
except Exception as e:
    logger.critical(f"An unexpected error occurred during database setup: {e}", exc_info=True)
    sys.exit(1)

# ======================================================================================
#                              *** Group Management ***
# ======================================================================================

async def add_group(group_id: int, group_name: str):
    """Adds a group to the list of approved groups for auto-search."""
    try:
        approved_groups.update_one(
            {'_id': group_id}, 
            {'$set': {'name': group_name, 'approved_on': datetime.now(timezone.utc)}}, 
            upsert=True
        )
    except OperationFailure as e:
        logger.error(f"DB Error adding group {group_id}: {e}")

async def remove_group(group_id: int):
    """Removes a group from the approved list."""
    try:
        approved_groups.delete_one({'_id': group_id})
    except OperationFailure as e:
        logger.error(f"DB Error removing group {group_id}: {e}")

async def get_approved_groups():
    """Gets a list of all approved group documents."""
    try:
        return list(approved_groups.find())
    except OperationFailure as e:
        logger.error(f"DB Error getting approved groups: {e}")
        return []

# ======================================================================================
#                              *** User Management ***
# ======================================================================================

async def add_user(user_id: int):
    try:
        user_data.update_one(
            {'_id': user_id},
            {'$set': {'banned': False}, '$setOnInsert': {'joined_date': datetime.now(timezone.utc)}},
            upsert=True
        )
    except OperationFailure as e:
        logger.error(f"DB Error adding user {user_id}: {e}")

async def get_user(user_id: int):
    try:
        return user_data.find_one({'_id': user_id})
    except OperationFailure as e:
        logger.error(f"DB Error getting user {user_id}: {e}")
        return None

async def is_user_present(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user) and not user.get('banned', False)

async def get_all_users():
    try:
        return list(user_data.find())
    except OperationFailure as e:
        logger.error(f"DB Error getting all users: {e}")
        return []

async def get_all_user_ids():
    try:
        return [doc['_id'] for doc in user_data.find({'banned': {'$ne': True}}, {'_id': 1})]
    except OperationFailure as e:
        logger.error(f"DB Error getting all user IDs: {e}")
        return []

async def ban_user(user_id: int):
    user_data.update_one({'_id': user_id}, {'$set': {'banned': True}}, upsert=True)

async def unban_user(user_id: int):
    user_data.update_one({'_id': user_id}, {'$set': {'banned': False}}, upsert=True)

async def delete_user(user_id: int):
    try:
        user_data.delete_one({'_id': user_id})
    except OperationFailure as e:
        logger.error(f"DB Error deleting user {user_id}: {e}")

# ======================================================================================
#                               *** Analytics & Stats ***
# ======================================================================================

async def log_file_download(file_id: int, user_id: int):
    try:
        analytics_data.insert_one({'file_id': file_id, 'user_id': user_id, 'timestamp': datetime.now(timezone.utc)})
    except OperationFailure as e:
        logger.error(f"DB Error logging download for file {file_id}: {e}")

async def get_daily_download_counts():
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_utc = today_utc - timedelta(days=1)
    day_before_utc = today_utc - timedelta(days=2)
    pipeline = [{'$facet': {'today': [{'$match': {'timestamp': {'$gte': today_utc}}}, {'$count': 'count'}], 'yesterday': [{'$match': {'timestamp': {'$gte': yesterday_utc, '$lt': today_utc}}}, {'$count': 'count'}], 'day_before': [{'$match': {'timestamp': {'$gte': day_before_utc, '$lt': yesterday_utc}}}, {'$count': 'count'}]}}]
    try:
        result = list(analytics_data.aggregate(pipeline))[0]
        today_count = result['today'][0]['count'] if result.get('today') and result['today'] else 0
        yesterday_count = result['yesterday'][0]['count'] if result.get('yesterday') and result['yesterday'] else 0
        day_before_count = result['day_before'][0]['count'] if result.get('day_before') and result['day_before'] else 0
        return today_count, yesterday_count, day_before_count
    except (OperationFailure, IndexError) as e:
        logger.error(f"DB Error getting daily counts: {e}")
        return 0, 0, 0

async def get_top_downloaded_files(days: int = 0):
    match_filter = {}
    if days > 0:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        match_filter = {'timestamp': {'$gte': start_date}}
    pipeline = [{'$match': match_filter} if match_filter else {'$match': {}}, {'$group': {'_id': '$file_id', 'count': {'$sum': 1}}}, {'$sort': {'count': -1}}, {'$limit': 5}, {'$lookup': {'from': 'file_index', 'localField': '_id', 'foreignField': '_id', 'as': 'file_details'}}, {'$unwind': '$file_details'}, {'$project': {'count': 1, 'file_name': '$file_details.file_name'}}]
    try:
        return list(analytics_data.aggregate(pipeline))
    except OperationFailure as e:
        logger.error(f"DB Error getting top files: {e}")
        return []

async def get_user_download_count(user_id: int):
    try:
        return analytics_data.count_documents({'user_id': user_id})
    except OperationFailure as e:
        logger.error(f"DB Error getting user download count for {user_id}: {e}")
        return 0

async def get_user_last_downloads(user_id: int, limit: int = 5):
    pipeline = [
        {'$match': {'user_id': user_id}},
        {'$sort': {'timestamp': -1}},
        {'$limit': limit},
        {'$lookup': {'from': 'file_index', 'localField': 'file_id', 'foreignField': '_id', 'as': 'file_details'}},
        {'$unwind': '$file_details'},
        {'$project': {'file_name': '$file_details.file_name', 'timestamp': 1}}
    ]
    try:
        return list(analytics_data.aggregate(pipeline))
    except OperationFailure as e:
        logger.error(f"DB Error getting user last downloads for {user_id}: {e}")
        return []

async def get_db_stats():
    try:
        stats = database.command("dbStats")
        return stats.get("storageSize", 0), stats.get("dataSize", 0)
    except OperationFailure as e:
        logger.error(f"DB Error getting dbStats: {e}")
        return 0, 0

async def get_total_file_stats():
    try:
        return file_index.count_documents({})
    except (OperationFailure, IndexError):
        return 0

# ======================================================================================
#                               *** File Indexing & Search ***
# ======================================================================================

async def add_file_to_index(message) -> str:
    file_id = message.id
    file_name = getattr(message.document, 'file_name', None) or getattr(message.video, 'file_name', None)
    if not file_name: return "failed"
    try:
        file_index.update_one(
            {'_id': file_id},
            {'$set': {'file_name': file_name, 'file_size': getattr(message.document or message.video, 'file_size', 0), 'date_added': message.date, 'duration': getattr(message.video, 'duration', 0) or 0}},
            upsert=True
        )
        return "new"
    except OperationFailure as e:
        logger.error(f"DB Error indexing file {file_id}: {e}")
        return "failed"

async def search_files(query: str, limit: int = 15):
    try:
        return list(file_index.find({'$text': {'$search': query}}, {'score': {'$meta': 'textScore'}}).sort([('score', {'$meta': 'textScore'})]).limit(limit))
    except OperationFailure as e:
        logger.error(f"DB Error during file search for query '{query}': {e}")
        return []
