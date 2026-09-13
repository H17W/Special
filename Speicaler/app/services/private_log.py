from app.core.database import db
def save_message(chat_id,message_id,sender_id,sender_name,sender_username,kind,text,media_type=None,media_path=None,created_at=None,edited_at=None):
 import time
 db.run('INSERT OR REPLACE INTO message_archive(chat_id,message_id,sender_id,sender_name,sender_username,kind,text,media_type,media_path,created_at,edited_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(chat_id,message_id,sender_id,sender_name,sender_username,kind,text or '',media_type,media_path,int(created_at or time.time()),edited_at))
def conversation(chat_id,limit=50,offset=0): return db.all('SELECT * FROM message_archive WHERE chat_id=? ORDER BY created_at,message_id LIMIT ? OFFSET ?',(chat_id,limit,offset))
def search_people(term,limit=20):
 term=f'%{term}%'; return db.all('SELECT DISTINCT chat_id,sender_id,sender_name,sender_username FROM message_archive WHERE sender_name LIKE ? OR sender_username LIKE ? OR CAST(sender_id AS TEXT) LIKE ? ORDER BY chat_id LIMIT ?',(term,term,term,limit))
