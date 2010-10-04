#!/usr/bin/python
from __future__ import with_statement

import tornado.httpserver
import tornado.ioloop
import tornado.web
import pymongo

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

class DocHandler(tornado.web.RequestHandler):
    def get(self, docId):
        con = pymongo.Connection('localhost')
        if docId:
            uid = 'urn:uuid:' + docId
            d = con.xds.docs.find_one({"entryUUID": uid})
            self.set_header("Content-Type", "text/plain")
            import simplejson as json
            del d['_id']
            s = json.dumps(d, sort_keys=True, indent=4)
            self.write(s)
        else:
            ds = [ d for d in con.xds.docs.find({},{"entryUUID":1},
                                                sort=[("creationTime", pymongo.DESCENDING)])]
            self.write('<h1>Documents</h1><ul>')
            for d in ds:
                docId = d['entryUUID'][9:]
                self.write("<li><a href='/docs/%s'>%s</a></li>" % (docId, docId))
            self.write('</ul>')
        con.disconnect()

import os
settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "static")
}
application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/docs/(.*)", DocHandler), 
], **settings)

reactor = tornado.ioloop.IOLoop.instance()
import time

def clbk():
    print 'Woke up!' + time.asctime(time.localtime())
    c = tornado.ioloop.PeriodicCallback(clbk2, 1000, reactor)
    c.start()
    print "ended"

def clbk():
    print('Woke up2!' + time.asctime(time.localtime()))
    print reactor._callbacks
    time.sleep(10)
    print "ended2"

if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8888)
    c = tornado.ioloop.PeriodicCallback(clbk, 5000, reactor)
    c.start()
    reactor.start()
               
