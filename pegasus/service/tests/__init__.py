import os
import unittest
import tempfile
import shutil
import base64

from flask import json

from pegasus.service import app, db, migrations, users

class TestCase(unittest.TestCase):

    def setUp(self):
        app.config.update(DEBUG=True)

        # Create a temp dir to store data files
        self.tmpdir = tempfile.mkdtemp()
        app.config.update(STORAGE_DIR=self.tmpdir)

        self.app = app.test_client()

    def tearDown(self):
        # Remove the temp dir
        shutil.rmtree(self.tmpdir)

class DBTestCase(TestCase):
    "This test case is for tests that require the database"

    def setUp(self):
        TestCase.setUp(self)
        self.dbfile = os.path.join(self.tmpdir, "workflow.db")
        self.dburi = "sqlite:///%s" % self.dbfile
        app.config.update(SQLALCHEMY_DATABASE_URI=self.dburi)
        migrations.create()

    def tearDown(self):
        db.session.remove()
        migrations.drop()
        os.remove(self.dbfile)
        TestCase.tearDown(self)

class APITestCase(DBTestCase):
    "This test case has a user scott with password tiger"

    def setUp(self):
        DBTestCase.setUp(self)

        # Create a test user
        self.username = "scott"
        self.password = "tiger"
        self.email = "scott@isi.edu"
        users.create(username=self.username, password=self.password, email=self.email)
        db.session.commit()

        # Patch the Flask/Werkzeug open to support required features
        orig_open = self.app.open
        def myopen(*args, **kwargs):
            headers = kwargs.get("headers", [])

            # Support basic authentication
            if kwargs.get("auth", True):
                userpass = self.username + ":" + self.password
                uphash = base64.b64encode(userpass)
                headers.append(("Authorization", "Basic %s" % uphash))
                kwargs.update(headers=headers)

            if "auth" in kwargs:
                del kwargs["auth"]

            r = orig_open(*args, **kwargs)

            # If the response is json, parse it
            r.json = None
            if r.content_type == "application/json":
                r.json = json.loads(r.data)

            return r

        self.app.open = myopen

        self.get = self.app.get
        self.post = self.app.post
        self.delete = self.app.delete
        self.put = self.app.put

    def tearDown(self):
        DBTestCase.tearDown(self)

from werkzeug.serving import make_server, BaseWSGIServer
import threading

class TestWSGIServer(threading.Thread):
    def __init__(self, *args, **kwargs):
        self.host = kwargs.pop("host")
        self.port = kwargs.pop("port")
        threading.Thread.__init__(self, *args, **kwargs)
        self.server = make_server(self.host, self.port, app=app)

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.join()

class ClientTestCase(APITestCase):

    def setUp(self):
        APITestCase.setUp(self)
        self.host = "127.0.0.1"
        self.port = 4999
        self.server = TestWSGIServer(host=self.host, port=self.port)
        self.server.start()

    def tearDown(self):
        self.server.shutdown()
        APITestCase.tearDown(self)

