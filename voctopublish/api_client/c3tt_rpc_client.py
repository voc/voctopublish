#    Copyright (C) 2021 derpeter
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

import hashlib
import hmac
import logging
import socket
import urllib
import xml
import xmlrpc.client


class C3TTClient:
    """
    group: worker group
    secret: client secret
    host: client hostname (will be taken from local host if set to None)
    url: tracker url (without the rpc)
    """

    def __init__(self, url, group, host, secret):
        self.url = url + "rpc"
        self.group = group
        self.host = host
        self.secret = secret

    def _gen_signature(self, method, args):
        """
        generate signature
        assemble static part of signature arguments
        1. URL  2. method name  3. worker group token  4. hostname
        :param method:
        :param args:
        :return: hmac signature
        """
        sig_args = urllib.parse.quote(
            self.url + "&" + method + "&" + self.group + "&" + self.host + "&", "~"
        )

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
                        kvs.append(
                            urllib.parse.quote('[' + str(k) + ']', '~')
                            + '='
                            + urllib.parse.quote(str(v), '~')
                        )
                    arg = '&'.join(kvs)
                else:
                    arg = urllib.parse.quote(str(arg), '~')

                sig_args = str(sig_args) + str(arg)
                if i < (len(args) - 1):
                    sig_args = sig_args + urllib.parse.quote('&')
                i += 1

        # generate the hmac hash with the key
        hash_ = hmac.new(
            bytes(self.secret, 'utf-8'), bytes(sig_args, 'utf-8'), hashlib.sha256
        )
        return hash_.hexdigest()

    def _open_rpc(self, method, ticket=None, args=None):
        """
        create xmlrpc client
        :param method:
        :param ticket: optional, either a numeric ticket_id or an instance of Ticket class
        :param args:
        :return: attributes of the answer
        """
        logging.debug(
            'creating XML RPC proxy: '
            + self.url
            + "?group="
            + self.group
            + "&hostname="
            + self.host
        )
        if args is None:
            args = []
        if ticket is not None:
            # the ticket parameter can be either a numeric ticket_id or an instance of Ticket class
            if isinstance(ticket, int) or isinstance(ticket, str):
                args.insert(0, ticket)
            else:
                args.insert(0, ticket.id)

        try:
            proxy = xmlrpc.client.ServerProxy(
                self.url + "?group=" + self.group + "&hostname=" + self.host
            )
        except xmlrpc.client.Fault as err:
            msg = "A fault occurred\n"
            msg += "Fault code: %d \n" % err.faultCode
            msg += "Fault string: %s" % err.faultString
            raise C3TTException(msg) from err

        except xmlrpc.client.ProtocolError as err:
            msg = "A protocol error occurred\n"
            msg += "URL: %s \n" % err.url
            msg += "HTTP/HTTPS headers: %s\n" % err.headers
            msg += "Error code: %d\n" % err.errcode
            msg += "Error message: %s" % err.errmsg
            raise C3TTException(msg) from err

        except socket.gaierror as err:
            msg = "A socket error occurred\n"
            msg += err
            raise C3TTException(msg) from err

        args.append(self._gen_signature(method, args))

        try:
            logging.debug(method + str(args))
            result = getattr(proxy, method)(*args)
        except xml.parsers.expat.ExpatError as err:
            msg = "A expat err occured\n"
            msg += err
            raise C3TTException(msg) from err
        except xmlrpc.client.Fault as err:
            msg = "A fault occurred\n"
            msg += "Fault code: %d\n" % err.faultCode
            msg += "Fault string: %s" % err.faultString
            raise C3TTException(msg) from err
        except xmlrpc.client.ProtocolError as err:
            msg = "A protocol error occurred\n"
            msg += "URL: %s\n" % err.url
            msg += "HTTP/HTTPS headers: %s\n" % err.headers
            msg += "Error code: %d\n" % err.errcode
            msg += "Error message: %s" % err.errmsg
            raise C3TTException(msg) from err
        except OSError as err:
            msg = "A OS error occurred\n"
            msg += "Error message: %s" % err
            raise C3TTException(msg) from err

        return result

    def get_version(self):
        """
        get Tracker Version
        :return: tracker version string
        """
        return str(self._open_rpc("C3TT.getVersion"))

    def assign_next_unassigned_for_state(
        self, ticket_type, to_state, property_filters=[]
    ):
        """
        check for new ticket on tracker and get assignment
        this also sets the ticket id in the c3tt client instance and has therefore be called before any ticket related
        function
        :param ticket_type: type of ticket
        :param to_state: ticket state the returned ticket will be in after this call
        :parm property_filters:  return only tickets matching given properties
        :return: ticket id or None in case no ticket is available for the type and state in the request
        """
        ret = self._open_rpc(
            "C3TT.assignNextUnassignedForState",
            args=[ticket_type, to_state, property_filters],
        )
        # if we get no xml here there is no ticket for this job
        if not ret:
            return None
        else:
            return ret

    def get_assigned_for_state(self, ticket_type, state, property_filters=[]):
        """
        Get first assigned ticket in state $state
        function
        :param ticket_type: type of ticket
        :param to_state: ticket state the returned ticket will be in after this call
        :parm property_filters: return only tickets matching given properties
        :return: ticket id or None in case no ticket is available for the type and state in the request
        """
        ret = self._open_rpc(
            "C3TT.getAssignedForState", args=[ticket_type, state, property_filters]
        )
        # if we get no xml here there is no ticket for this job
        if not ret:
            return None
        else:
            if len(ret) > 1:
                logging.warn("multiple tickets assined, fetching first one")
            return ret[0]

    def get_tickets_for_state(self, ticket_type, to_state, property_filters=[]):
        """
        Get all tickets in state $state from projects assigned to the workerGroup, unless workerGroup is halted
        function
        :param ticket_type: type of ticket
        :param to_state: ticket state the returned ticket will be in after this call
        :parm property_filters: return only tickets matching given properties
        :return: ticket id or None in case no ticket is available for the type and state in the request
        """
        ret = self._open_rpc(
            "C3TT.getTicketsForState", args=[ticket_type, to_state, property_filters]
        )
        # if we get no xml here there is no ticket for this job
        if not ret:
            return None
        else:
            return ret

    def set_ticket_properties(self, ticket, properties):
        """
        set ticket properties
        :param ticket:
        :param properties:
        :return: Boolean
        """
        ret = self._open_rpc("C3TT.setTicketProperties", ticket, args=[properties])
        if not ret:
            logging.error("no xml in answer")
            return False
        else:
            return True

    def get_ticket_properties(self, ticket):
        """
        get ticket properties
        :return:
        """
        ret = self._open_rpc("C3TT.getTicketProperties", ticket)
        if not ret:
            logging.error("no xml in answer")
            return None
        else:
            return ret

    def set_ticket_done(self, ticket, message=None):
        """
        set Ticket status on done
        :return:
        """
        if message is not None:
            ret = self._open_rpc("C3TT.setTicketDone", ticket, [message])
        else:
            ret = self._open_rpc("C3TT.setTicketDone", ticket)
        logging.debug(str(ret))

    def set_ticket_failed(self, ticket, error):
        """
        set ticket status on failed an supply a error text
        :param ticket: id of ticket
        :param error:
        """
        self._open_rpc(
            "C3TT.setTicketFailed", ticket, [error.encode('ascii', 'xmlcharrefreplace')]
        )

    def create_encoding_ticket(self, ticket, profile):
        """
        create a encoding ticket below a meta ticket
        :ticket: the ticket id or a ticket object
        :profile: id of the encoding profile
        :properties: an array of properties (optional)
        """
        ret = self._open_rpc("C3TT.createEncodingTicket", ticket, args=[profile])
        return ret

    def create_meta_ticket(
        self, project: int, title: str, fahrplan_id: int, properties=None
    ):
        """
        create a new meta ticket in a project
        :param project: id of the project
        :param title: title of the ticket
        :param fahrplan_id: id of the talk in fahrplan
        :param properties: optional list of properties
        """
        args = [project, title, fahrplan_id]
        if properties:
            args.append(properties)

        ret = self._open_rpc('C3TT.createMetaTicket', args=args)
        return ret


class C3TTException(Exception):
    pass
