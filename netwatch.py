#! /usr/local/bin/python

"""
NETWATCH

is a script which pings specified hosts on a regular interval
and sends out a notification email after a specific timeout

Copyright (c) 2018, Andy KAYL
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the <organization> nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

# hosts definitions are dictionaries within a tuple
# the dicitonary contains following keys:
# "name" => is used as description for the machine
# "address" => is used to check host availability
# "ports => is used to test services (set to None to ignore port testing or use a list of ports)
hosts = (
    {"name": "My Server 1", "address": "192.168.0.1", "ports": [80, 443]},
    {"name": "My Server 2", "address": "192.168.0.2", "ports": [53]},
)

# check interval for ping requests (in seconds)
# only used in daemon mode
check_interval = 120

# email send interval (in seconds)
# only used in daemon mode
email_interval = 1800

# email sender domain
email_domain = "mysenderdomain.net"

# email sending server
email_server = "mail.mymail.com"

# email sending user
email_user = "smtpuser@mymail.com"

# email sending password
email_pass = "smtppass"

# email server port
email_port = 587

# set ewmail recipients as string or tuple
email_to = ("rcpt1@mymail.com", "rcpt2@mymail.com")

# set how many ICMP packets will be sent
icmp_count = 3

# set timeout for every ICMP packets (in seconds)
icmp_timeout = 1

"""-----------------------------------------------------------------------
DO NOT EDIT PAST THIS LINE!!!
-----------------------------------------------------------------------"""

__author__ = "Andy KAYL (andy@codex.lu)"
__version__ = 1.7

import os
import sys
import subprocess
import smtplib
import re
import sqlite3
import tempfile
import time
import signal
import socket
import traceback

from email.mime.text import MIMEText


class NetWatch(object):
    
    def __init__(self):
        self.initDatabase()
        self.loop_locked = False
        self.is_daemon = False
        self.grep_command = "ps ax | grep -E '%s (-d|--daemon)'"
    
    def initDatabase(self):
        self.db = sqlite3.connect(os.path.join(tempfile.gettempdir(), "netwatch.db"))
        self.dbcursor = self.db.cursor()
        self.dbcursor.execute(
            """CREATE TABLE IF NOT EXISTS hosts (
                date Integer,
                host Text,
                address Text,
                status Boolean
            )"""
        )
        self.dbcursor.execute("CREATE TABLE IF NOT EXISTS sendings (date Integer)")
        try:
            self.dbcursor.execute("CREATE INDEX hostsIdx ON hosts (date, status)")
        except sqlite3.OperationalError:
            pass
        try:
            self.dbcursor.execute("ALTER TABLE hosts ADD COLUMN loss Integer")
        except sqlite3.OperationalError:
            pass
        try:
            self.dbcursor.execute("ALTER TABLE hosts ADD COLUMN failedports Text")
        except sqlite3.OperationalError:
            pass
    
    def resetDatabase(self):
        os.remove(os.path.join(tempfile.gettempdir(), "netwatch.db"))
    
    def clearDatabase(self):
        deadline = int(time.time()) - (24*60*60)
        self.dbcursor.execute("DELETE FROM hosts WHERE date<?", [deadline])
        self.dbcursor.execute("DELETE FROM sendings WHERE date<?", [deadline])
        self.db.commit()
    
    def analyse(self):
        self.host_status = []
        for machine in hosts:
            state = 0
            ports = []
            date = time.strftime("%d.%m.%Y %H:%M:%S")
            
            sys.stdout.write("[%s] Checking: %s" % (date, machine['name']))
            sys.stdout.flush()
            
            loss = self.pingHost(machine['address'])
            if loss == 0 and machine['ports'] is not None:
                ports = self.testPorts(machine['address'], machine['ports'])
            
            if loss == 0 and len(ports) == 0:
                sys.stdout.write(" = GOOD")
                state = 1
            elif loss == 0 and len(ports) > 0:
                for port in ports:
                    sys.stdout.write("\n\t = BAD - service on port %s is not reachable!" % port)
            elif loss > 0 and loss < 100:
                sys.stdout.write(" = BAD - unstable (%d%% loss)! please verify!" % loss)
            elif loss == 100:
                sys.stdout.write(" = BAD - not available (%d%% loss)! please verify!" % loss)
            
            my_host = {
                "name": machine['name'],
                "address": machine['address'],
                "state": state,
                "time": int(time.time()),
                "loss": loss,
                "failedports": ":".join(ports)
            }
            self.host_status.append(my_host)
            
            sys.stdout.write("\n")
            sys.stdout.flush()
    
    def pingHost(self, address):
        cmd = "ping -c %s -i %s %s" % (icmp_count, icmp_timeout, address)
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        out, err = proc.communicate()
        match = re.search("\s{1,}([0-9]{1,3})(\.0)?% packet loss", out.strip(), re.IGNORECASE)
        return int(match.group(1))
    
    def testPorts(self, address, ports):
        failed = []
        if ports is None:
            return failed
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((address, port))
            except Exception as e:
                failed.append(str(port))
            finally:
                sock.close()
        return failed
    
    def saveStatus(self):
        for host in self.host_status:
            self.dbcursor.execute(
                "INSERT INTO hosts (date, host, address, status, loss, failedports) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    host['time'],
                    host['name'],
                    host['address'],
                    host['state'],
                    host['loss'],
                    host['failedports']
                ]
            )
        self.db.commit()
    
    def testSending(self):
        now = int(time.time())
        self.dbcursor.execute("SELECT date FROM sendings ORDER BY date DESC LIMIT 1")
        res_sending = self.dbcursor.fetchall()
        if len(res_sending) == 0:
            self.dbcursor.execute("INSERT INTO sendings (date) VALUES (?)", [now])
            self.db.commit()
            return True
        latest_sending = int(res_sending[0][0])
        res_hosts = self.getInvalidHosts()
        cnt_unavail = len(res_hosts)
        if self.is_daemon and now - latest_sending > email_interval and cnt_unavail > 0:
            return True
        elif not self.is_daemon:
            return True
        return False
    
    def getInvalidHosts(self):
        deadline_date = 300
        if self.is_daemon:
            deadline_date = int(time.time()) - email_interval
        self.dbcursor.execute(
            "SELECT DISTINCT date, host, loss, failedports FROM hosts WHERE date>? AND status=0",
            [deadline_date]
        )
        return self.dbcursor.fetchall()
    
    def sendEmail(self):
        if not self.testSending():
            return
        res_hosts = self.getInvalidHosts()
        if len(res_hosts) == 0:
            return
        
        print "Errors found... sending email."
        email_from = "netwatch@%s" % email_domain
        
        mytext = "Following hosts had availability or port errors:\n\n"
        for row in res_hosts:
            mytext += "Time: %s\n" % time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(row[0]))
            mytext += "\tHost: %s\n" % row[1]
            if int(row[2]) == 100:
                msg_state = "unavailable"
            elif int(row[2] == 0):
                msg_state = "stable"
            else:
                msg_state = "unstable"
            mytext += "\tConnection: %s (%s%% loss)\n" % (msg_state, row[2])
            if row[3] != "":
                ports = row[3].split(":")
                mytext += '\tPorts: service on %s is unavailable\n' % ", ".join(ports)
            mytext += "\n"
        
        msg = MIMEText(mytext)
        msg['Subject'] = "NetWatch detected unavailable host(s)"
        msg['From'] = email_from
        msg['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S +0200", time.localtime())
        
        smtp = smtplib.SMTP()
        try:
            smtp.connect(email_server, email_port)
        except socket.error as e:
            print "Error mail sending: %s" % e
            return
        except socket.gaierror as e:
            print "Error mail sending: %s" % e
            return
        smtp.ehlo_or_helo_if_needed()
        smtp.starttls()
        try:
            smtp.login(email_user, email_pass)
        except smtplib.SMTPAuthenticationError:
            print "Error: Authentication failed"
            return
        if isinstance(email_to, str):
            msg['To'] = email_to
            smtp.sendmail(email_from, email_to, msg.as_string())
        elif isinstance(email_to, tuple) or isinstance(email_to, list):
            for addr in email_to:
                msg['To'] = addr
                smtp.sendmail(email_from, addr, msg.as_string())
        smtp.quit()
        
        self.dbcursor.execute("INSERT INTO sendings (date) VALUES (?)", [int(time.time())])
        self.db.commit()
    
    def stopDaemon(self):
        scriptname = sys.argv[0]
        proc = subprocess.Popen(
            self.grep_command % scriptname,
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        proc.wait()
        out, err = proc.communicate()
        pid_list = []
        for line in out.split("\n"):
            match = re.search("^\s*[0-9]+ ", line, re.IGNORECASE)
            if match:
                pid_list.append(int(match.group(0)))
        for pid in pid_list:
            os.kill(pid, signal.SIGTERM)
            print "Process %s killed." % pid
        try:
            os.unlink(os.path.join("/", "var", "run", "netwatch.pid"))
        except OSError as e:
            pass
    
    def printStatus(self):
        scriptname = sys.argv[0]
        proc = subprocess.Popen(
            self.grep_command % scriptname,
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        proc.wait()
        out, err = proc.communicate()
        pid_list = []
        for line in out.strip().split("\n"):
            match = re.search("^\s*[0-9]+ ", line, re.IGNORECASE)
            if match:
                print "Running... PID = %s" % int(match.group(0))
            else:
                print "Not running..."
                break
    
    def startOnce(self):
        self.clearDatabase()
        self.analyse()
        self.saveStatus()
        self.sendEmail()
    
    def startDaemon(self):
        self.is_daemon = True
        pidfile = os.path.join("/", "var", "run", "netwatch.pid")
        if os.path.isfile(pidfile):
            print "PID file %s already exists!? Not starting." % pidfile
            sys.exit(1)
        execpath = os.path.sep.join(os.path.abspath(sys.argv[0]).split(os.path.sep)[0:-1])
        sys.stdout = open(os.path.join(execpath, "/var/log/netwatch.log"), "a")
        pid = os.fork()
        if pid > 0:
            fh = open(pidfile, "w")
            fh.write(str(pid))
            fh.close()
            os._exit(0)
        while True:
            try:
                if self.loop_locked:
                    print "still scanning... skipping..."
                else:
                    self.loop_locked = True
                    self.clearDatabase()
                    self.analyse()
                    self.saveStatus()
                    self.sendEmail()
                print "sleeping for %s seconds..." % check_interval
            except Exception as e:
                print "ERROR: %s" % str(e)
            finally:
                self.loop_locked = False
            sys.stdout.flush()
            time.sleep(check_interval)
    
if __name__ == '__main__':
    netwatch = NetWatch()
    if "-h" in sys.argv or "--help" in sys.argv or len(sys.argv) > 2:
        print """
Usage:
%s <parameter>

Parameter can be one of the following:
    -d, --daemon|--start    starts the script as background process
    -s, --stop              stops all background processes
    -p, --status            print script process IDs
    -r, --reset             resets/removes database
    -h, --help              display this help screen
""" % sys.argv[0]
    elif "-p" in sys.argv or "--status" in sys.argv:
        netwatch.printStatus()
    elif "-s" in sys.argv or "--stop" in sys.argv:
        netwatch.stopDaemon()
    elif "-d" in sys.argv or "--daemon" in sys.argv or "--start" in sys.argv:
        netwatch.startDaemon()
    elif "-r" in sys.argv or "--reset" in sys.argv:
        netwatch.resetDatabase()
    else:
        netwatch.startOnce()
    sys.exit(0)
