import unittest
from unittest.mock import patch, Mock
import requests # For requests.exceptions.RequestException

# Assuming ixcsoft_service.py is in the same directory or PYTHONPATH is set up
from ixcsoft_service import fetch_client_address, fetch_clients

# Mock environment variables if they are accessed at module level in ixcsoft_service
# For simplicity, we assume they are primarily used within functions or Flask app context,
# which might not be directly hit by these specific unit tests if functions are pure enough.
# If direct os.getenv is problematic at import time for tests, further mocking is needed.
# For now, we proceed assuming functions can be tested somewhat in isolation.

class TestFetchClientAddress(unittest.TestCase):

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_success(self, mock_get):
        # Configure the mock for a successful response
        mock_response = Mock()
        mock_response.json.return_value = {'bairro': 'Centro', 'endereco': 'Rua Principal 123'}
        mock_response.raise_for_status = Mock() # Does nothing for success
        mock_get.return_value = mock_response

        client_id = '1'
        expected_address = {'bairro': 'Centro', 'endereco': 'Rua Principal 123'}

        # Mock host, as it's used to build the URL
        # Also mock the global headers from the module to ensure the test checks against the correct object/value
        mocked_global_headers = {'Authorization': 'Basic mock_token_base64', 'Content-Type': 'application/json'}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'), \
             patch('ixcsoft_service.ixcsoft_service.headers', mocked_global_headers):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 200)
        self.assertEqual(result_data, expected_address)
        mock_get.assert_called_once_with(
            f"https://mock_host/webservice/v1/cliente/{client_id}",
            headers=mocked_global_headers,
            verify=False
        )

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_api_error(self, mock_get):
        # Configure the mock for an API error response
        mock_response = Mock()
        mock_response.json.return_value = {'type': 'error', 'message': 'Client not found'}
        # For HTTPError simulation, if raise_for_status is based on this, it might need specific setup
        # However, fetch_client_address checks for 'type':'error' even in 200 responses from IXC.
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client_id = '2'
        expected_error_data = {'error': 'Client not found'}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 404)
        self.assertEqual(result_data, expected_error_data)

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_http_error_from_ixc(self, mock_get):
        # Test for when IXC API itself returns a 4xx/5xx error
        mock_response = Mock()
        mock_response.status_code = 403 # Example: Forbidden from IXC
        mock_response.json.return_value = {'message': 'Access denied by IXC'}
        mock_response.text = 'Access denied by IXC'
        mock_get.return_value = mock_response
        mock_get.side_effect = requests.exceptions.HTTPError(response=mock_response)

        client_id = '2b'
        expected_error_data = {'error': 'IXC API HTTP error: 403', 'details': 'Access denied by IXC'}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 403)
        self.assertEqual(result_data, expected_error_data)


    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_request_exception(self, mock_get):
        # Configure the mock to raise a RequestException
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        client_id = '3'
        expected_error_data = {'error': 'Failed to connect to IXC API: Network error'}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 503)
        self.assertEqual(result_data, expected_error_data)

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_missing_fields(self, mock_get):
        # Configure the mock for a response with missing fields
        mock_response = Mock()
        mock_response.json.return_value = {'bairro': 'Vila Nova'} # Missing 'endereco'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client_id = '4'
        expected_address = {'bairro': 'Vila Nova', 'endereco': None}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 200)
        self.assertEqual(result_data, expected_address)

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_json_decode_error(self, mock_get):
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Error decoding JSON", "doc", 0)
        # Important: raise_for_status should not be called before .json() if .json() is the one failing
        # or if it is, ensure it doesn't throw an exception that masks JSONDecodeError
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client_id = '5'
        expected_error_data = {'error': 'Invalid JSON response from IXC API'}
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            result_data, status_code = fetch_client_address(client_id)

        self.assertEqual(status_code, 502)
        self.assertEqual(result_data, expected_error_data)


class TestFetchClients(unittest.TestCase):

    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_success(self, mock_post):
        # Configure mock for requests.post (radusuarios)
        mock_post_response = Mock()
        sample_registros = [
            {'id_cliente': '101', 'login': 'user1', 'conexao': 'ppp1', 'ultima_conexao_final': 'today', 'id_transmissor': 'tx1', 'latitude': '0', 'longitude': '0'},
            {'id_cliente': '102', 'login': 'user2', 'conexao': 'ppp2', 'ultima_conexao_final': 'yesterday', 'id_transmissor': 'tx2', 'latitude': '1', 'longitude': '1'}
        ]
        mock_post_response.json.return_value = {
            'registros': sample_registros,
            'total': str(len(sample_registros))
        }
        mock_post_response.raise_for_status = Mock()
        mock_post.return_value = mock_post_response

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('offline')

        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0]['login'], 'user1')
        self.assertEqual(clients[0]['id_cliente'], '101')
        self.assertNotIn('bairro', clients[0])
        self.assertNotIn('endereco', clients[0])

        self.assertEqual(clients[1]['login'], 'user2')
        self.assertEqual(clients[1]['id_cliente'], '102')
        self.assertNotIn('bairro', clients[1])
        self.assertNotIn('endereco', clients[1])

    # test_fetch_clients_address_fetch_returns_none has been removed as it's no longer relevant.

    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_no_id_cliente(self, mock_post):
        # Test case where 'id_cliente' is missing in the registro
        mock_post_response = Mock()
        sample_registros = [
            {'login': 'user4', 'conexao': 'ppp4', 'ultima_conexao_final': 'today', 'id_transmissor': 'tx4', 'latitude': '3', 'longitude': '3'} # No id_cliente
        ]
        mock_post_response.json.return_value = {
            'registros': sample_registros,
            'total': str(len(sample_registros))
        }
        mock_post_response.raise_for_status = Mock()
        mock_post.return_value = mock_post_response

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('offline')

        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]['login'], 'user4')
        self.assertNotIn('bairro', clients[0]) # bairro should not be present
        self.assertNotIn('endereco', clients[0]) # endereco should not be present
        # id_cliente might be None or not present, depending on .get() behavior if key is missing vs present with None value
        self.assertIsNone(clients[0].get('id_cliente'))


    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_api_error_radusuarios(self, mock_post):
        # Test case where the radusuarios API itself returns an error
        mock_post_response = Mock()
        mock_post_response.json.return_value = {'type': 'error', 'message': 'Failed to fetch radusuarios'}
        mock_post_response.raise_for_status = Mock() # Or could raise an HTTPError that is caught
        mock_post.return_value = mock_post_response

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('offline')

        self.assertEqual(len(clients), 0) # Should return an empty list on API error

    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_request_exception_radusuarios(self, mock_post):
        # Test case where the radusuarios API call raises a network exception
        mock_post.side_effect = requests.exceptions.RequestException("Network error for radusuarios")

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('offline')

        self.assertEqual(len(clients), 0)


if __name__ == '__main__':
    unittest.main()


# Test class for the new Flask route
from ixcsoft_service.ixcsoft_service import app # Import the Flask app instance
import json # For json.loads

class TestClientAddressRoute(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        # It's often good practice to patch at the class level if multiple tests use the same mock
        self.requests_get_patcher = patch('ixcsoft_service.ixcsoft_service.requests.get')
        self.mock_requests_get = self.requests_get_patcher.start()

        # Mock host and headers for all route tests, as fetch_client_address uses them
        self.host_patcher = patch('ixcsoft_service.ixcsoft_service.host', 'mock_external_ixc_host')
        self.mock_host = self.host_patcher.start()

        self.headers_patcher = patch('ixcsoft_service.ixcsoft_service.headers', {'Authorization': 'Basic TestToken', 'Content-Type': 'application/json'})
        self.mock_headers = self.headers_patcher.start()


    def tearDown(self):
        self.requests_get_patcher.stop()
        self.host_patcher.stop()
        self.headers_patcher.stop()

    def test_route_success(self):
        mock_response = Mock()
        mock_response.json.return_value = {'bairro': 'Test Bairro', 'endereco': 'Test Endereco'}
        mock_response.raise_for_status = Mock()
        self.mock_requests_get.return_value = mock_response

        response = self.client.get('/cliente/123')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data, {'bairro': 'Test Bairro', 'endereco': 'Test Endereco'})
        self.mock_requests_get.assert_called_once_with(
            f"https://mock_external_ixc_host/webservice/v1/cliente/123",
            headers={'Authorization': 'Basic TestToken', 'Content-Type': 'application/json'},
            verify=False,
            timeout=10
        )

    def test_route_client_not_found_external_api_error(self):
        # Simulate external IXC API returning its own "not found" error, e.g., in a 200 response's JSON
        mock_response = Mock()
        mock_response.json.return_value = {'type': 'error', 'message': 'Cliente nao encontrado no IXC'}
        mock_response.raise_for_status = Mock() # No HTTPError raised by requests.get
        self.mock_requests_get.return_value = mock_response

        response = self.client.get('/cliente/404_id')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(data, {'error': 'Cliente nao encontrado no IXC'})

    def test_route_client_not_found_external_api_http_404(self):
        # Simulate external IXC API returning an actual HTTP 404
        mock_ext_response = Mock(status_code=404)
        mock_ext_response.json.return_value = {'message': 'IXC Nao Encontrado'} # Example IXC 404 body
        mock_ext_response.text = 'IXC Nao Encontrado'
        self.mock_requests_get.side_effect = requests.exceptions.HTTPError(response=mock_ext_response)

        response = self.client.get('/cliente/404_real_id')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 404)
        self.assertIn('IXC API HTTP error: 404', data['error'])
        self.assertEqual(data['details'], 'IXC Nao Encontrado')


    def test_route_external_api_server_error(self):
        mock_ext_response = Mock(status_code=500)
        mock_ext_response.json.return_value = {'message': 'Erro interno no IXC'}
        mock_ext_response.text = 'Erro interno no IXC'
        self.mock_requests_get.side_effect = requests.exceptions.HTTPError(response=mock_ext_response)

        response = self.client.get('/cliente/500_id')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 500)
        self.assertIn('IXC API HTTP error: 500', data['error'])

    def test_route_network_error_to_external_api(self):
        self.mock_requests_get.side_effect = requests.exceptions.RequestException("Cannot connect to IXC")

        response = self.client.get('/cliente/net_error_id')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(data, {'error': 'Failed to connect to IXC API: Cannot connect to IXC'})

    def test_route_invalid_json_from_external_api(self):
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("IXC returned malformed JSON", "doc", 0)
        self.mock_requests_get.return_value = mock_response

        response = self.client.get('/cliente/bad_json_id')
        data = json.loads(response.data.decode('utf-8'))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(data, {'error': 'Invalid JSON response from IXC API'})
```