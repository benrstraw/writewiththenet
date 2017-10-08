from http.server import BaseHTTPRequestHandler, HTTPServer
import mysql.connector as mariadb
import time
import urllib
import json
import secrets

HOST_NAME = 'localhost'
PORT_NUMBER = 8462

class WriteWithTheNet(BaseHTTPRequestHandler):
	def do_GET(self):
		paths = {
			'/get_line'		: go_get_line	# no input
		}

		if self.path in paths:
			paths[self.path](self)
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


def go_get_line(self):
	self.send_response(200)
	self.send_header("Content-Type", "text/plain")
	self.end_headers()

	stories = [
		"Once upon a time, there was some code.",
		"You're at Knight Hacks 2017, when suddenly...",
		"\"Dude, I'm super hungry,\" said your best friend Ben.",
		"You are a cow. Moo.",
		"And with that,you become the first person to step foot on Mars."
	]

	self.wfile.write(secrets.choice(stories).encode())
	return

def go_post_line(self, post_data):
	post_vars = urllib.parse.parse_qs(post_data)
	print(post_vars)
	post_vars['new_line']

	#database stuff
	# new_story_id = the stuff
	new_story_id = 1234 # testing

	self.send_response(303)
	self.send_header("Location", "/story?id=" + str(new_story_id))
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

	print(time.asctime(), 'Server Stops - %s:%s' % (HOST_NAME, PORT_NUMBER))