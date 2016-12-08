#    Copyright (C) 2016 derpeter
#    derpeter@berlin.ccc.de
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import xmlrpc.client
import hashlib
import hmac
import socket
import urllib
import xml
import logging

from ticket_module import Ticket


class C3TClient:
    """
    group: worker group
    secret: client secret
    host: client hostname (will be taken from local host if set to None)
    url: tracker url (without the rpc)
    """

    def __init__(self, t: Ticket, url, group, host, secret):
        self.t = t
        self.url = url + "rpc"
        self.group = group
        self.host = host
        self.secret = secret

    def __gen_signature(self, method, args):
        """
        generate signature
        assemble static part of signature arguments
        1. URL  2. method name  3. worker group token  4. hostname
        :param method:
        :param args:
        :return:
        """
        sig_args = urllib.parse.quote(self.url + "&" + method + "&" + self.group + "&" + self.host + "&", "~")

        # add method args
        if len(args) > 0:
            i = 0
            while i < len(args):
                arg = args[i]
                if isinstance(arg, bytes):
                    arg = arg.decode()
                if isinstance(arg, dict):
                    kvs = []
                    for k, v in args[i].items():
                        kvs.append(urllib.parse.quote('[' + k + ']', '~') + '=' + urllib.parse.quote(v, '~'))
                    arg = '&'.join(kvs)
                else:
                    arg = urllib.parse.quote(str(arg), '~')

                sig_args = str(sig_args) + str(arg)
                if i < (len(self.args) - 1):
                    sig_args = sig_args + urllib.parse.quote('&')
                i += 1

        # generate the hmac hash with the key
        hash = hmac.new(bytes(self.secret, 'utf-8'), bytes(sig_args, 'utf-8'), hashlib.sha256)
        return hash.hexdigest()

    def __open_rpc(self, method, args):
        """
        create xmlrpc client
        :param method:
        :param args:
        :return:
        """
        logging.debug('creating XML RPC proxy: ' + self.url + "?group=" + self.group + "&hostname=" + self.host)
        try:
            proxy = xmlrpc.client.ServerProxy(self.url + "?group=" + self.group + "&hostname=" + self.host)
        except xmlrpc.client.Fault as err:
            msg = "A fault occurred\n"
            msg += "Fault code: %d \n" % err.faultCode
            msg += "Fault string: %s" % err.faultString
            raise C3TTExcption(msg) from err

        except xmlrpc.client.ProtocolError as err:
            msg = "A protocol error occurred\n"
            msg += "URL: %s \n" % err.url
            msg += "HTTP/HTTPS headers: %s\n" % err.headers
            msg += "Error code: %d\n" % err.errcode
            msg += "Error message: %s" % err.errmsg
            raise C3TTExcption(msg) from err

        except socket.gaierror as err:
            msg = "A socket error occurred\n"
            msg += err
            raise C3TTExcption(msg) from err

        except xmlrpc.client.ProtocolError as err:
            msg = "A Protocol occurred\n"
            msg += err
            raise C3TTExcption(msg) from err

        args.append(self.__gen_signature(method, args))

        try:
            logging.debug(method + str(args))
            result = getattr(proxy, method)(*args)
        except xml.parsers.expat.ExpatError as err:
            msg = "A expat err occured\n"
            msg += err
            raise C3TTExcption(msg) from err
        except xmlrpc.client.Fault as err:
            msg = "A fault occurred\n"
            msg += "Fault code: %d\n" % err.faultCode
            msg += "Fault string: %s" % err.faultString
            raise C3TTExcption(msg) from err
        except xmlrpc.client.ProtocolError as err:
            msg = "A protocol error occurred\n"
            msg += "URL: %s\n" % err.url
            msg += "HTTP/HTTPS headers: %s\n" % err.headers
            msg += "Error code: %d\n" % err.errcode
            msg += "Error message: %s" % err.errmsg
            raise C3TTExcption(msg) from err
        except OSError as err:
            msg = "A OS error occurred\n"
            msg += "Error code: %d\n" % err.errcode
            msg += "Error message: %s" % err.errmsg
            raise C3TTExcption(msg) from err

        return result

    def getVersion(self):
        """
        get Tracker Version
        :return:
        """
        tmp_args = ["1"];
        return str(self.__open_rpc("C3TT.getVersion", tmp_args))

    def assignNextUnassignedForState(self, from_state, to_state):
        """
        check for new ticket on tracker an get assignement
        :param from_state:
        :param to_state:
        :return:
        """
        tmp_args = [from_state, to_state]
        ret = self.__open_rpc("C3TT.assignNextUnassignedForState", tmp_args)
        # if get no xml there seems to be no ticket for this job
        if not ret:
            return False
        else:
            return ret['id']

    def setTicketProperties(self, id, properties):
        """
        set ticket properties
        :param id:
        :param properties:
        :return:
        """
        tmp_args = [id, properties]
        ret = self.__open_rpc("C3TT.setTicketProperties", tmp_args)
        if not ret:
            logging.error("no xml in answer")
            return False
        else:
            return True

    def getTicketProperties(self, id):
        """
        get ticket properties
        :param id:
        :return:
        """
        tmp_args = [id]
        ret = self.__open_rpc("C3TT.getTicketProperties", tmp_args)
        if not ret:
            logging.error("no xml in answer")
            return None
        else:
            return ret

    def setTicketDone(self, id):
        """
        set Ticket status on done
        :param id:
        :return:
        """
        tmp_args = [id]
        ret = self.__open_rpc("C3TT.setTicketDone", tmp_args)
        logging.debug(ret)

    def setTicketFailed(self, id, error):
        """
        set ticket status on failed an supply a error text
        :param id:
        :param error:
        :return:
        """
        enc_error = error.encode('ascii', 'xmlcharrefreplace')
        tmp_args = [id, enc_error]
        self.__open_rpc("C3TT.setTicketFailed", tmp_args)


class C3TTExcption(Exception):
    pass
