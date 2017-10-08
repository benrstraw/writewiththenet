from http.server import BaseHTTPRequestHandler, HTTPServer
from http import cookies
import mysql.connector as mariadb
import time
import urllib
import json
import secrets
import random
from private_data import *

HOST_NAME = 'localhost'
PORT_NUMBER = 8462

MAX_LINES_PER_STORY = 25
MAX_REQS_BEFORE_NEW = 10
SEEN_LIVE_TIME = 0

CURRENT_REQUESTS = 0

stories = [
	"Once upon a time, there was some code.",
	"You're at Knight Hacks 2017, when suddenly...",
	"\"Dude, I'm super hungry,\" said your best friend Ben.",
	"You are a cow. Moo.",
	"And with that, you become the first person to step foot on Mars."
]

mariadb_connection = mariadb.connect(user='root', password=private_db_password, database='writewiththenet')
cursor = mariadb_connection.cursor()

class WriteWithTheNet(BaseHTTPRequestHandler):
	def do_GET(self):
		paths = {
			'/get_line'		: go_get_line,
			'/get_story'	: go_get_story,
			'/cookie_test'	: go_cookie_test
		}

		if urllib.parse.urlparse(self.path).path in paths:
			paths[urllib.parse.urlparse(self.path).path](self)
		else:
			self.send_response(500)
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
			self.send_response(500)
			self.end_headers()

		return

def go_cookie_test(self):
	if "Cookie" in self.headers:
		print "Cookies found: " + self.headers["Cookie"]
	else:
		print "No cookies."

	self.send_response(200)
	self.send_header("Content-Type", "application/json")
	self.send_header("Set-Cookie", "test=rando")
	self.end_headers()
	
	return

def go_get_story(self):
	get_vars = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
	if "id" not in get_vars:
		self.send_response(500)
		self.end_headers()
		return

	self.send_response(200)
	self.send_header("Content-Type", "application/json")
	self.end_headers()

	cursor.execute("SELECT line_text FROM story_lines WHERE story_id = %s", (get_vars['id'][0],))
	thelines = cursor.fetchall()
	print(json.dumps(thelines))
	resp = json.dumps(thelines)

#	resp = "{\"text\":\"" + line_text + "\",\"left\":" + str(lines_left) + ",\"story_id\":" + str(story_id) + "}"

	self.wfile.write(resp.encode())
	return

def go_get_line(self):
	self.send_response(200)
	self.send_header("Content-Type", "application/json")

	global CURRENT_REQUESTS
	CURRENT_REQUESTS += 1

	line_text = ""
	lines_left = 999
	story_id = -1
	if CURRENT_REQUESTS >= MAX_REQS_BEFORE_NEW:
		line_text = secrets.choice(stories)
		cursor.execute("SELECT MAX(story_id) FROM story_lines")
		story_id = cursor.fetchone()[0] + 1

		try:
			cursor.execute("INSERT INTO story_lines (story_id, line_text) VALUES (%s,%s)", (story_id, line_text))
		except mariadb.Error as error:
			print("Error: {}".format(error))
			return
		mariadb_connection.commit()
		CURRENT_REQUESTS = 0
	else:
		#cursor.execute("SELECT line_text FROM story_lines WHERE last_seen < NOW() - INTERVAL 5 MINUTE ORDER BY ID DESC LIMIT 1")
		cursor.execute("""SELECT * FROM
			(SELECT * FROM story_lines WHERE line_id IN (SELECT MAX(line_id) FROM story_lines GROUP BY story_id HAVING COUNT(*) <= %s) ORDER BY line_id DESC) AS last_lines
			WHERE last_seen < NOW() - INTERVAL %s MINUTE""", (MAX_LINES_PER_STORY, SEEN_LIVE_TIME))

		recents = cursor.fetchall()
		if not recents:
			line_text = secrets.choice(stories)
			cursor.execute("SELECT MAX(story_id) FROM story_lines")
			last_story_id = cursor.fetchone()[0]
			if last_story_id:
				story_id = last_story_id + 1
			else:
				story_id = 1

			try:
				cursor.execute("INSERT INTO story_lines (story_id, line_text) VALUES (%s,%s)", (story_id, line_text))
			except mariadb.Error as error:
				print("Error: {}".format(error))
				return
			mariadb_connection.commit()
		else:
			new_line_id = secrets.choice(recents)[0]
			cursor.execute("SELECT line_text, story_id FROM story_lines WHERE line_id = %s", (new_line_id,))
			res = cursor.fetchone()
			line_text = res[0]
			story_id = int(res[1])
			cursor.execute("UPDATE story_lines SET last_seen = NOW() WHERE line_id = %s", (new_line_id,))
			mariadb_connection.commit()


		cursor.execute("SELECT COUNT(story_id) FROM story_lines WHERE story_id = %s", (story_id,))
		lines_left = MAX_LINES_PER_STORY - cursor.fetchone()[0]

	self.end_headers()

	kvjson = {}
	kvjson["text"] = line_text
	kvjson["left"] = lines_left
	kvjson["story_id"] = story_id

	resp = json.dumps(kvjson)
	print(resp)

	#resp = "{\"text\":\"" + line_text + "\",\"left\":" + str(lines_left) + ",\"story_id\":" + str(story_id) + "}"

	self.wfile.write(resp.encode())
	return

def go_post_line(self, post_data):
	if not post_data:
		self.send_response(500)
		self.end_headers()
		return
	
	post_vars = urllib.parse.parse_qs(post_data)
	
	if "new_line" not in post_vars or "story_id" not in post_vars:
		self.send_response(501)
		self.end_headers()
		return

	print(post_vars)
	print(post_vars['new_line'])
	print(post_vars['new_line'][0])

	try:
		cursor.execute("INSERT INTO story_lines (story_id, line_text) VALUES (%s,%s)", (post_vars['story_id'][0], post_vars['new_line'][0]))
	except mariadb.Error as error:
		print("Error: {}".format(error))

	mariadb_connection.commit()

	line_number = 2
	self.send_response(303)
	self.send_header("Location", "/story?id=" + str(post_vars['story_id'][0]) )# + "&line=" + str(line_number))
	self.end_headers()
	return

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