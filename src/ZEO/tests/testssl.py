import mock
import os
import ssl
import unittest
from ZODB.config import storageFromString

from ..Exceptions import ClientDisconnected
from .. import runzeo

from .testConfig import ZEOConfigTest

here = os.path.dirname(__file__)
server_cert = os.path.join(here, 'server.pem')
server_key  = os.path.join(here, 'server_key.pem')
serverpw_cert = os.path.join(here, 'serverpw.pem')
serverpw_key  = os.path.join(here, 'serverpw_key.pem')
client_cert = os.path.join(here, 'client.pem')
client_key  = os.path.join(here, 'client_key.pem')

class SSLConfigTest(ZEOConfigTest):

    def test_ssl_basic(self):
        # This shows that configuring ssl has an actual effect on connections.
        # Other SSL configuration tests will be Mockiavellian.

        # Also test that an SSL connection mismatch doesn't kill
        # the server loop.

        # An SSL client can't talk to a non-SSL server:
        addr, stop = self.start_server()
        with self.assertRaises(ClientDisconnected):
            self.start_client(
                addr,
                """<ssl>
                certificate {}
                key {}
                </ssl>""".format(client_cert, client_key), wait_timeout=1)

        # But a non-ssl one can:
        client = self.start_client(addr)
        self._client_assertions(client, addr)
        client.close()
        stop()

        # A non-SSL client can't talk to an SSL server:
        addr, stop = self.start_server(
            """<ssl>
            certificate {}
            key {}
            authenticate {}
            </ssl>""".format(server_cert, server_key, client_cert)
            )
        with self.assertRaises(ClientDisconnected):
            self.start_client(addr, wait_timeout=1)

        # But an SSL one can:
        client = self.start_client(
            addr,
            """<ssl>
                certificate {}
                key {}
                authenticate {}
                </ssl>""".format(client_cert, client_key, server_cert))
        self._client_assertions(client, addr)
        client.close()
        stop()

    def test_ssl_hostname_check(self):
        addr, stop = self.start_server(
            """<ssl>
            certificate {}
            key {}
            authenticate {}
            </ssl>""".format(server_cert, server_key, client_cert)
            )

        # Connext with bad hostname fails:

        with self.assertRaises(ClientDisconnected):
            client = self.start_client(
                addr,
                """<ssl>
                    certificate {}
                    key {}
                    authenticate {}
                    server-hostname example.org
                    </ssl>""".format(client_cert, client_key, server_cert),
                wait_timeout=1)

        # Connext with good hostname succeeds:
        client = self.start_client(
            addr,
            """<ssl>
                certificate {}
                key {}
                authenticate {}
                server-hostname zodb.org
                </ssl>""".format(client_cert, client_key, server_cert))
        self._client_assertions(client, addr)
        client.close()
        stop()

    def test_ssl_pw(self):
        addr, stop = self.start_server(
            """<ssl>
            certificate {}
            key {}
            authenticate {}
            password-function ZEO.tests.testssl.pwfunc
            </ssl>""".format(serverpw_cert, serverpw_key, client_cert)
            )
        stop()

    @mock.patch('ssl.create_default_context')
    def test_ssl_mockiavellian_server_no_ssl(self, factory):
        server = create_server()
        self.assertFalse(factory.called)
        self.assertEqual(server.acceptor._Acceptor__ssl, None)
        server.close()

    def assert_context(
        self, factory, context,
        cert=(server_cert, server_key, None),
        verify_mode=ssl.CERT_REQUIRED,
        check_hostname=False,
        cafile=None, capath=None,
        ):
        factory.assert_called_with(
            ssl.Purpose.CLIENT_AUTH, cafile=cafile, capath=capath)
        context.load_cert_chain.assert_called_with(*cert)
        self.assertEqual(context, factory.return_value)
        self.assertEqual(context.verify_mode, verify_mode)
        self.assertEqual(context.check_hostname, check_hostname)

    @mock.patch('ssl.create_default_context')
    def test_ssl_mockiavellian_server_ssl_no_auth(self, factory):
        with self.assertRaises(SystemExit):
            # auth is required
            create_server(certificate=server_cert, key=server_key)

    @mock.patch('ssl.create_default_context')
    def test_ssl_mockiavellian_server_ssl_auth_file(self, factory):
        server = create_server(
            certificate=server_cert, key=server_key, authenticate=__file__)
        context = server.acceptor._Acceptor__ssl
        self.assert_context(factory, context, cafile=__file__)
        server.close()

    @mock.patch('ssl.create_default_context')
    def test_ssl_mockiavellian_server_ssl_auth_dir(self, factory):
        server = create_server(
            certificate=server_cert, key=server_key, authenticate=here)
        context = server.acceptor._Acceptor__ssl
        self.assert_context(factory, context, capath=here)
        server.close()

    @mock.patch('ssl.create_default_context')
    def test_ssl_mockiavellian_server_ssl_pw(self, factory):
        server = create_server(
            certificate=server_cert,
            key=server_key,
            password_function='ZEO.tests.testssl.pwfunc',
            authenticate=here,
            )
        context = server.acceptor._Acceptor__ssl
        self.assert_context(
            factory, context, (server_cert, server_key, pwfunc), capath=here)
        server.close()

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_no_ssl(self, ClientStorage, factory):
        client = ssl_client()
        self.assertFalse('ssl' in ClientStorage.call_args[1])
        self.assertFalse('ssl_server_hostname' in ClientStorage.call_args[1])

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_server_signed(
        self, ClientStorage, factory
        ):
        client = ssl_client(certificate=client_cert, key=client_key)
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         None)
        self.assert_context(
            factory, context, (client_cert, client_key, None),
            check_hostname=True)

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_auth_dir(
        self, ClientStorage, factory
        ):
        client = ssl_client(
            certificate=client_cert, key=client_key, authenticate=here)
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         None)
        self.assert_context(
            factory, context, (client_cert, client_key, None),
            capath=here,
            )

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_auth_file(
        self, ClientStorage, factory
        ):
        client = ssl_client(
            certificate=client_cert, key=client_key, authenticate=server_cert)
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         None)
        self.assert_context(
            factory, context, (client_cert, client_key, None),
            cafile=server_cert,
            )

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_pw(
        self, ClientStorage, factory
        ):
        client = ssl_client(
            certificate=client_cert, key=client_key,
            password_function='ZEO.tests.testssl.pwfunc',
            authenticate=server_cert)
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         None)
        self.assert_context(
            factory, context, (client_cert, client_key, pwfunc),
            check_hostname=False,
            cafile=server_cert,
            )

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_server_hostname(
        self, ClientStorage, factory
        ):
        client = ssl_client(
            certificate=client_cert, key=client_key, authenticate=server_cert,
            server_hostname='example.com')
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         'example.com')
        self.assert_context(
            factory, context, (client_cert, client_key, None),
            cafile=server_cert,
            check_hostname=True,
            )

    @mock.patch('ssl.create_default_context')
    @mock.patch('ZEO.ClientStorage.ClientStorage')
    def test_ssl_mockiavellian_client_check_hostname(
        self, ClientStorage, factory
        ):
        client = ssl_client(
            certificate=client_cert, key=client_key, authenticate=server_cert,
            check_hostname=True)
        context = ClientStorage.call_args[1]['ssl']
        self.assertEqual(ClientStorage.call_args[1]['ssl_server_hostname'],
                         None)
        self.assert_context(
            factory, context, (client_cert, client_key, None),
            cafile=server_cert,
            check_hostname=True,
            )

def args(*a, **kw):
    return a, kw

def ssl_conf(**ssl_settings):
    if ssl_settings:
        ssl_conf = '<ssl>\n' + '\n'.join(
            '{} {}'.format(name.replace('_', '-'), value)
            for name, value in ssl_settings.items()
            ) + '\n</ssl>\n'
    else:
        ssl_conf = ''

    return ssl_conf

def ssl_client(**ssl_settings):
    return storageFromString(
        """%import ZEO

        <clientstorage>
          server localhost:0
          {}
        </clientstorage>
        """.format(ssl_conf(**ssl_settings))
        )

def create_server(**ssl_settings):
    with open('conf', 'w') as f:
        f.write(
            """
            <zeo>
              address localhost:0
              {}
            </zeo>
            <mappingstorage>
            </mappingstorage>
            """.format(ssl_conf(**ssl_settings)))

    options = runzeo.ZEOOptions()
    options.realize(['-C', 'conf'])
    s = runzeo.ZEOServer(options)
    s.open_storages()
    s.create_server()
    return s.server

pwfunc = lambda : '1234'


def test_suite():
    return unittest.makeSuite(SSLConfigTest)

# Helpers for other tests:

server_config = """
    <zeo>
      address 127.0.0.1:0
      <ssl>
        certificate {}
        key {}
        authenticate {}
      </ssl>
    </zeo>
    """.format(server_cert, server_key, client_cert)

def client_ssl():
    context = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH, cafile=server_cert)

    context.load_cert_chain(client_cert, client_key)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = False
    return context
