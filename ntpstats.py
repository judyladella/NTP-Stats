import ntplib
from time import ctime

# Create client and query NTP server
client = ntplib.NTPClient()
response = client.request('pool.ntp.org', version=3)

# Offset: Local clock difference from server in seconds
# A negative value means your local clock is ahead.
print(f"Offset: {response.offset} seconds")
print(f"Delay: {response.delay} seconds")
print(f"Server time: {ctime(response.tx_time)}")
