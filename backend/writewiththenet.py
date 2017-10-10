#!/usr/bin/env python
# -*- coding: utf-8 -*-

from http.server import BaseHTTPRequestHandler, HTTPServer
from http import cookies
import mysql.connector as mariadb
import time
import urllib
import json
import secrets
import random
import threading
import sys
from private_data import *

HOST_NAME = 'localhost'
PORT_NUMBER = 8462

MAX_LINES_PER_STORY = 25
REQUESTS_BEFORE_NEW_STORY = 15
SEEN_LIVE_TIME = 150 #seconds
SESSION_LIFETIME = 150 #seconds

CURRENT_REQUESTS = 0

story_sessions = {}

stories = [
	"Once upon a time, there was some code.",
	"You're at Knight Hacks 2017, when suddenly...",
	"\"Dude, I'm super hungry,\" said your best friend Ben.",
	"You are a cow. Moo.",
	"And with that, you become the first person to step foot on Mars."
]

mariadb_connection = mariadb.connect(unix_socket='/run/mysqld/mysqld.sock', host='localhost', user=private_db_user, password=private_db_password, database=private_db_database)
cursor = mariadb_connection.cursor()

class WriteWithTheNet(BaseHTTPRequestHandler):
	def log_message(self, format, *args):
		print("[%s] - %s > %s" %
							(self.log_date_time_string(),
							self.headers['X-Real-IP'],
							 format%args))

	def do_GET(self):
		paths = {
			'/get_line'		: go_get_line,
			'/get_story'	: go_get_story,
			'/cookie_test'	: go_cookie_test
		}

		if urllib.parse.urlparse(self.path).path in paths:
			paths[urllib.parse.urlparse(self.path).path](self)
		else:
			self.send_response(400)
			self.end_headers()

		return

	def do_POST(self):
		length = int(self.headers['Content-Length'])
		type = self.headers['Content-Type']
		raw_post_data = self.rfile.read(length).decode('utf-8')

		#post_vars = urllib.parse.parse_qs(raw_post_data)
		#post_json = json.loads(raw_post_data)

		paths = {
			'/post_line'	: go_post_line	# plain text input
		}

		if self.path in paths:
			paths[self.path](self, raw_post_data)
		else:
			self.send_response(400)
			self.end_headers()

		return

def go_cookie_test(self):
	if "Cookie" in self.headers:
		print("Cookies found: " + self.headers["Cookie"])
	else:
		print("No cookies.")

	ruuid = random.randint(1, 10000000000)
	self.send_response(200)
	self.send_header("Content-Type", "application/json")
	self.send_header("Set-Cookie", "user=" + str(ruuid) + "; Expires: Wed, 01 Jan 2025 00:00:00 GMT")
	self.end_headers()

#	self.wfile.write(str(story_sessions).encode())

	return

def go_get_story(self):
	get_vars = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
	if "id" not in get_vars:
		self.send_response(400)
		self.end_headers()
		return

	self.send_response(200)
	self.send_header("Content-Type", "application/json")
	self.end_headers()

	cursor.execute("SELECT line_text FROM wtn_lines WHERE story_id = %s", (get_vars['id'][0],))
	thelines = cursor.fetchall()
	resp = json.dumps(thelines)

	self.wfile.write(resp.encode())
	return

def go_get_line(self):
	self.send_response(200)
	self.send_header("Content-Type", "application/json")

	ruuid = 0
	if "Cookie" in self.headers:
		C = cookies.BaseCookie(self.headers["Cookie"])
		if "user" in C:
			ruuid = C["user"].value
		else:
			ruuid = random.randint(1, 2147483648)
			self.send_header("Set-Cookie", "user=" + str(ruuid) + "; Expires: Wed, 01 Jan 2025 00:00:00 GMT")
	else:
		ruuid = random.randint(1, 2147483648)
		self.send_header("Set-Cookie", "user=" + str(ruuid) + "; Expires: Wed, 01 Jan 2025 00:00:00 GMT")

	global CURRENT_REQUESTS
	CURRENT_REQUESTS += 1

	line_text = ""
	lines_left = 999
	story_id = -1
	if CURRENT_REQUESTS >= REQUESTS_BEFORE_NEW_STORY:
		line_text = secrets.choice(stories)
		cursor.execute("SELECT MAX(story_id) FROM wtn_lines")
		story_id = cursor.fetchone()[0] + 1

		print(" +> Request threshold reached. Inserting new story with ID = " + str(story_id))

		try:
			cursor.execute("INSERT INTO wtn_lines (story_id, line_text) VALUES (%s,%s)", (story_id, line_text))
		except mariadb.Error as error:
			print("Error: {}".format(error))
			return
		mariadb_connection.commit()
		CURRENT_REQUESTS = 0
	else:
		#cursor.execute("SELECT line_text FROM wtn_lines WHERE last_seen < NOW() - INTERVAL 5 MINUTE ORDER BY ID DESC LIMIT 1")
		cursor.execute("""SELECT * FROM
			(SELECT * FROM wtn_lines WHERE line_id IN
			(SELECT MAX(line_id) FROM wtn_lines GROUP BY story_id HAVING COUNT(*) <= %s)
			AND line_id NOT IN (SELECT line_id FROM wtn_lines WHERE user_id <> %s)
			ORDER BY line_id DESC) AS last_lines
			WHERE last_seen < NOW() - INTERVAL %s SECOND""", (ruuid, MAX_LINES_PER_STORY, SEEN_LIVE_TIME))

#		cursor.execute("""SELECT * FROM
#			(SELECT * FROM wtn_lines WHERE line_id IN (SELECT MAX(line_id) FROM wtn_lines GROUP BY story_id HAVING COUNT(*) <= %s) ORDER BY line_id DESC) AS last_lines
#			WHERE last_seen < NOW() - INTERVAL %s SECOND""", (MAX_LINES_PER_STORY, SEEN_LIVE_TIME))

		recents = cursor.fetchall()
		if not recents:
			line_text = secrets.choice(stories)
			cursor.execute("SELECT MAX(story_id) FROM wtn_lines")
			last_story_id = cursor.fetchone()[0]
			if last_story_id:
				story_id = last_story_id + 1
			else:
				story_id = 1

			print(" +> No acceptable stories found for user " + str(ruuid) + ", inserting new story with ID = " + str(story_id))

			try:
				cursor.execute("INSERT INTO wtn_lines (story_id, line_text) VALUES (%s,%s)", (story_id, line_text))
			except mariadb.Error as error:
				print("Error: {}".format(error))
				return
			mariadb_connection.commit()
		else:
			new_line_id = secrets.choice(recents)[0]
			cursor.execute("SELECT line_text, story_id FROM wtn_lines WHERE line_id = %s", (new_line_id,))
			res = cursor.fetchone()
			line_text = res[0]
			story_id = int(res[1])
			cursor.execute("UPDATE wtn_lines SET last_seen = NOW() WHERE line_id = %s", (new_line_id,))
			mariadb_connection.commit()


		cursor.execute("SELECT COUNT(story_id) FROM wtn_lines WHERE story_id = %s", (story_id,))
		lines_left = MAX_LINES_PER_STORY - cursor.fetchone()[0]

	story_session = random.randint(1, 2147483648)

	global story_sessions
	while(story_session in story_sessions):
		story_session = random.randint(1, 2147483648)

	story_sessions[story_session] = story_id

	t = threading.Thread(target=rem_session_after_time, args=[story_session])
	t.start()

	print(" => Saved session " + str(story_session) + " as story ID " + str(story_sessions[story_session]))

	self.send_header("Set-Cookie", "story_session=" + str(story_session) + "")
	self.end_headers()

	kvjson = {}
	kvjson["text"] = line_text
	kvjson["left"] = lines_left
	kvjson["story_session"] = story_session

	resp = json.dumps(kvjson)
	print(" => get_line responding with: " + str(resp))

	#resp = "{\"text\":\"" + line_text + "\",\"left\":" + str(lines_left) + ",\"story_id\":" + str(story_id) + "}"

	self.wfile.write(resp.encode())
	return

def go_post_line(self, post_data):
	global story_sessions

	if not post_data:
		print(" => No POST data?!")
		self.send_response(400)
		self.end_headers()
		return

	post_vars = urllib.parse.parse_qs(post_data)

	if "new_line" not in post_vars or "story_session" not in post_vars:
		print(" => Missing POST vars: " + str(post_vars))
		self.send_response(400)
		self.end_headers()
		return

	new_story_session = int(post_vars['story_session'][0])
	if new_story_session not in story_sessions:
		print(" => Invalid story session of " + str(new_story_session) + ". Sessions: " + str(story_sessions))
		self.send_response(400)
		self.end_headers()
		return

	story_id = story_sessions[new_story_session]
	del story_sessions[new_story_session]

	if "Cookie" in self.headers:
		C = cookies.BaseCookie(self.headers["Cookie"])
		if "user" in C:
			ruuid = C["user"].value

	try:
		if ruuid:
			print(" <= User " + str(ruuid) + " submitted to post_line: " + str(post_vars))
			cursor.execute("INSERT INTO wtn_lines (story_id, line_text, user_id) VALUES (%s,%s,%s)", (story_id, post_vars['new_line'][0], ruuid))
		else:
			print(" <= Anonymous user submitted to post_line: " + str(post_vars))
			cursor.execute("INSERT INTO wtn_lines (story_id, line_text) VALUES (%s,%s)", (story_id, post_vars['new_line'][0]))
	except mariadb.Error as error:
		print("Error: {}".format(error))

	mariadb_connection.commit()

#	line_number = 2
	self.send_response(303)
	self.send_header("Location", "/story?id=" + str(story_id) )# + "&line=" + str(line_number))
	self.end_headers()
	return

def rem_session_after_time(session_key):
	time.sleep(SESSION_LIFETIME)
	global story_sessions
	if session_key in story_sessions:
		print(" ~> Session " + str(session_key) + " for story ID " + str(story_sessions[session_key]) + " timing out.")
		del story_sessions[session_key]

if __name__ == '__main__':
	server_class = HTTPServer
	httpd = server_class((HOST_NAME, PORT_NUMBER), WriteWithTheNet)

	print(time.asctime(), 'Server Starts - %s:%s' % (HOST_NAME, PORT_NUMBER))

	try:
		httpd.serve_forever()
	except KeyboardInterrupt:
		pass

	httpd.server_close()

	mariadb_connection.commit()
	mariadb_connection.close()

	print(time.asctime(), 'Server Stops - %s:%s' % (HOST_NAME, PORT_NUMBER))
