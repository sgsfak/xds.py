#### Configuration!!
# the repository id
MY_REPO_ID= '1.2.826.0.1.3680043.2.44.248240.2'

# the hostname of the MongoDB
MONGO_HOST = "localhost"

# The TCP port that the XDS server listens to
XDS_LISTEN_PORT = 9080

#The TCP port that the UB server listens to
# (for the web admin interface, e.g. http://localhost:9081/)
UB_LISTEN_PORT = 9081

# The TCP port that the UB server listens to for receiving
# notifications from the XDS server
UB_NOTIFY_PORT = UB_LISTEN_PORT + 1

# The maximum time in seconds that the UB server waits before
# checking the submissions
UB_CHK_TIMEOUT = 30 * 60
