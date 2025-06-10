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
            address = fetch_client_address(client_id)

        self.assertEqual(address, expected_address)
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
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client_id = '2'
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            address = fetch_client_address(client_id)

        self.assertIsNone(address)

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_request_exception(self, mock_get):
        # Configure the mock to raise a RequestException
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        client_id = '3'
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            address = fetch_client_address(client_id)

        self.assertIsNone(address)

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
            address = fetch_client_address(client_id)

        self.assertEqual(address, expected_address)

    @patch('ixcsoft_service.ixcsoft_service.requests.get')
    def test_fetch_client_address_json_decode_error(self, mock_get):
        mock_response = Mock()
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Error decoding JSON", "doc", 0)
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client_id = '5'
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            address = fetch_client_address(client_id)
        self.assertIsNone(address)


class TestFetchClients(unittest.TestCase):

    @patch('ixcsoft_service.ixcsoft_service.fetch_client_address') # Mock the local function
    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_success_with_address(self, mock_post, mock_fetch_address):
        # Configure mock for requests.post (radusuarios)
        mock_post_response = Mock()
        mock_post_response.json.return_value = {
            'registros': [
                {'id_cliente': '101', 'login': 'user1', 'ultima_conexao_final': 'today', 'id_transmissor': 'tx1', 'latitude': '0', 'longitude': '0'},
                {'id_cliente': '102', 'login': 'user2', 'ultima_conexao_final': 'yesterday', 'id_transmissor': 'tx2', 'latitude': '1', 'longitude': '1'}
            ],
            'total': '2'
        }
        mock_post_response.raise_for_status = Mock()
        mock_post.return_value = mock_post_response

        # Configure mock for fetch_client_address
        def side_effect_fetch_address(client_id):
            if client_id == '101':
                return {'bairro': 'Bairro A', 'endereco': 'Rua A'}
            if client_id == '102':
                return {'bairro': 'Bairro B', 'endereco': 'Rua B'}
            return None
        mock_fetch_address.side_effect = side_effect_fetch_address

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('offline')

        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0]['login'], 'user1')
        self.assertEqual(clients[0]['bairro'], 'Bairro A')
        self.assertEqual(clients[0]['endereco'], 'Rua A')
        self.assertEqual(clients[1]['login'], 'user2')
        self.assertEqual(clients[1]['bairro'], 'Bairro B')
        self.assertEqual(clients[1]['endereco'], 'Rua B')

        mock_fetch_address.assert_any_call('101')
        mock_fetch_address.assert_any_call('102')
        self.assertEqual(mock_fetch_address.call_count, 2)

    @patch('ixcsoft_service.ixcsoft_service.fetch_client_address')
    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_address_fetch_returns_none(self, mock_post, mock_fetch_address):
        # Configure mock for requests.post
        mock_post_response = Mock()
        mock_post_response.json.return_value = {
            'registros': [
                {'id_cliente': '201', 'login': 'user3', 'ultima_conexao_final': 'today', 'id_transmissor': 'tx3', 'latitude': '2', 'longitude': '2'}
            ],
            'total': '1'
        }
        mock_post_response.raise_for_status = Mock()
        mock_post.return_value = mock_post_response

        # Configure mock for fetch_client_address to return None
        mock_fetch_address.return_value = None

        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
            clients = fetch_clients('online') # Status doesn't matter much for this specific test focus

        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]['login'], 'user3')
        self.assertIsNone(clients[0]['bairro'])
        self.assertIsNone(clients[0]['endereco'])
        mock_fetch_address.assert_called_once_with('201')

    @patch('ixcsoft_service.ixcsoft_service.requests.post')
    def test_fetch_clients_no_id_cliente(self, mock_post):
        # Test case where 'id_cliente' is missing in the registro
        mock_post_response = Mock()
        mock_post_response.json.return_value = {
            'registros': [
                {'login': 'user4', 'ultima_conexao_final': 'today', 'id_transmissor': 'tx4', 'latitude': '3', 'longitude': '3'} # No id_cliente
            ],
            'total': '1'
        }
        mock_post_response.raise_for_status = Mock()
        mock_post.return_value = mock_post_response

        # We don't need to mock fetch_client_address here as it shouldn't be called
        with patch('ixcsoft_service.ixcsoft_service.host', 'mock_host'):
             with patch('ixcsoft_service.ixcsoft_service.fetch_client_address') as mock_fetch_addr_func:
                clients = fetch_clients('offline')
                mock_fetch_addr_func.assert_not_called()


        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]['login'], 'user4')
        self.assertIsNone(clients[0]['bairro'])
        self.assertIsNone(clients[0]['endereco'])

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
