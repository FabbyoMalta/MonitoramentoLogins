import unittest
from unittest.mock import patch, Mock, call # import call
import json

# Assuming alert_service.py is in the same directory or PYTHONPATH is set up
from alert_service import send_telegram_alert

# Mock environment variables for Telegram if they are accessed at module level.
# Similar to ixcsoft_service, we assume they are primarily used within functions
# or app context. send_telegram_alert uses os.getenv for token and chat_id,
# so those need to be available or patched. For simplicity in unit tests,
# we often patch the direct usage, e.g., the requests.post call or the config variables if imported.
# Let's patch the os.getenv calls within the scope of the tests for send_telegram_alert

@patch.dict('alert_service.alert_service.os.environ', {
    'TELEGRAM_BOT_TOKEN': 'fake_token',
    'TELEGRAM_CHAT_ID': 'fake_chat_id'
})
class TestSendTelegramAlert(unittest.TestCase):

    @patch('alert_service.alert_service.requests.post')
    def test_no_clients(self, mock_post):
        result = send_telegram_alert([], 'offline', 'TestConnection')
        self.assertEqual(result, {'message': 'Nenhum cliente para alertar'})
        mock_post.assert_not_called()

    @patch('alert_service.alert_service.requests.post')
    def test_online_clients(self, mock_post):
        clients = [{'login': 'user1', 'ultima_conexao_final': 'today', 'bairro': 'Centro', 'endereco': 'Rua A'}]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = send_telegram_alert(clients, 'online', 'TestConnection')

        self.assertEqual(result, {'message': 'Alerta enviado com sucesso no Telegram'})
        mock_post.assert_called_once()

        args, kwargs = mock_post.call_args
        payload = kwargs['data']
        self.assertEqual(payload['chat_id'], 'fake_chat_id')
        self.assertIn("✅ *Alerta: Todos os clientes voltaram a ficar online na conexão TestConnection.*", payload['text'])
        self.assertNotIn("Endereços afetados:", payload['text'])
        self.assertNotIn("Login:", payload['text']) # No client list for online status

    @patch('alert_service.alert_service.requests.post')
    def test_offline_clients_with_full_address_data(self, mock_post):
        clients = [
            {'login': 'user1', 'ultima_conexao_final': '2023-01-01 10:00', 'bairro': 'Centro', 'endereco': 'Rua A'},
            {'login': 'user2', 'ultima_conexao_final': '2023-01-01 11:00', 'bairro': 'Vila', 'endereco': 'Rua B'},
            {'login': 'user3', 'ultima_conexao_final': '2023-01-01 12:00', 'bairro': 'Centro', 'endereco': 'Rua C'}
        ]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_telegram_alert(clients, 'offline', 'TestConnectionXYZ')

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]['data'] # call_args[1] is kwargs

        self.assertIn("🚨 *Alerta: 3 clientes offline detectados na conexão TestConnectionXYZ.*", payload['text'])
        self.assertIn("*Endereços afetados:*", payload['text'])
        self.assertIn("📍 *Bairro:* Centro", payload['text'])
        self.assertIn("  - Rua A", payload['text'])
        self.assertIn("  - Rua C", payload['text'])
        self.assertIn("📍 *Bairro:* Vila", payload['text'])
        self.assertIn("  - Rua B", payload['text'])
        self.assertIn("- *Login:* `user1`", payload['text'])
        self.assertIn("  *Última conexão:* 2023-01-01 10:00", payload['text'])
        self.assertIn("- *Login:* `user3`", payload['text'])

    @patch('alert_service.alert_service.requests.post')
    def test_offline_clients_with_missing_address_data(self, mock_post):
        clients = [
            {'login': 'user1', 'ultima_conexao_final': '2023-01-01 10:00', 'bairro': 'Centro', 'endereco': None}, # Missing street
            {'login': 'user2', 'ultima_conexao_final': '2023-01-01 11:00', 'bairro': None, 'endereco': 'Rua B'},     # Missing neighborhood
            {'login': 'user3', 'ultima_conexao_final': '2023-01-01 12:00', 'bairro': 'Vila', 'endereco': 'Rua C'},
            {'login': 'user4', 'ultima_conexao_final': '2023-01-01 13:00', 'bairro': 'Centro', 'endereco': 'Rua D'}
        ]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_telegram_alert(clients, 'offline', 'TestConn')

        payload = mock_post.call_args[1]['data']
        self.assertIn("🚨 *Alerta: 4 clientes offline detectados na conexão TestConn.*", payload['text'])
        self.assertIn("*Endereços afetados:*", payload['text'])
        self.assertIn("📍 *Bairro:* Centro", payload['text'])
        self.assertIn("  - Rua D", payload['text'])
        self.assertIn("  - Rua não especificada", payload['text']) # For user1 with missing street
        self.assertIn("📍 *Bairro:* Vila", payload['text'])
        self.assertIn("  - Rua C", payload['text'])
        self.assertNotIn("Rua B", payload['text']) # user2's street should not appear as bairro is missing

        self.assertIn("- *Login:* `user1`", payload['text']) # All users should be listed
        self.assertIn("- *Login:* `user2`", payload['text'])
        self.assertIn("- *Login:* `user3`", payload['text'])
        self.assertIn("- *Login:* `user4`", payload['text'])

    @patch('alert_service.alert_service.requests.post')
    def test_offline_clients_no_address_data_at_all(self, mock_post):
        clients = [
            {'login': 'userA', 'ultima_conexao_final': '2023-01-02 10:00'},
            {'login': 'userB', 'ultima_conexao_final': '2023-01-02 11:00'}
        ]
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_telegram_alert(clients, 'offline', 'TestConnNoAddress')

        payload = mock_post.call_args[1]['data']
        self.assertIn("🚨 *Alerta: 2 clientes offline detectados na conexão TestConnNoAddress.*", payload['text'])
        # Endereços afetados section might be absent or indicate none found, current code generates empty string if no valid addresses.
        # Depending on exact string output for "no addresses", this assertion might need adjustment.
        # Based on current logic, an empty `enderecos_por_bairro` means `enderecos_afetados_str` is empty.
        self.assertNotIn("*Endereços afetados:*", payload['text'])

        self.assertIn("- *Login:* `userA`", payload['text'])
        self.assertIn("- *Login:* `userB`", payload['text'])

    @patch('alert_service.alert_service.requests.post')
    def test_custom_message(self, mock_post):
        clients = [{'login': 'user1', 'ultima_conexao_final': 'today', 'bairro': 'Centro', 'endereco': 'Rua A'}]
        custom_msg = "Attention! This is a custom alert."
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_telegram_alert(clients, 'offline', 'TestConnection', mensagem_personalizada=custom_msg)

        payload = mock_post.call_args[1]['data']
        self.assertTrue(payload['text'].startswith(custom_msg))
        # Also check if address info is still appended
        self.assertIn("📍 *Bairro:* Centro", payload['text'])
        self.assertIn("  - Rua A", payload['text'])

    @patch('alert_service.alert_service.MAX_CLIENTS_IN_MESSAGE', 2) # Test with a smaller max
    @patch('alert_service.alert_service.requests.post')
    def test_offline_clients_exceeding_max_message_with_mixed_addresses(self, mock_post):
        clients = [
            {'login': 'user1', 'ultima_conexao_final': '2023-01-01 10:00', 'bairro': 'Centro', 'endereco': 'Rua A'}, # Has address, will be listed
            {'login': 'user2', 'ultima_conexao_final': '2023-01-01 11:00', 'bairro': None, 'endereco': None},         # No address, will be listed
            {'login': 'user3', 'ultima_conexao_final': '2023-01-01 12:00', 'bairro': 'Vila', 'endereco': 'Rua B'}     # Has address, NOT listed by login due to MAX_CLIENTS
        ] # 3 clients, MAX_CLIENTS_IN_MESSAGE is 2

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        send_telegram_alert(clients, 'offline', 'TestConnectionMaxMixed')

        payload = mock_post.call_args[1]['data']
        self.assertIn("🚨 *Alerta: 3 clientes offline detectados na conexão TestConnectionMaxMixed.*", payload['text'])

        # Address synthesis should include user1 and user3, but not user2
        self.assertIn("*Endereços afetados:*", payload['text'])
        self.assertIn("📍 *Bairro:* Centro", payload['text'])
        self.assertIn("  - Rua A", payload['text']) # From user1
        self.assertIn("📍 *Bairro:* Vila", payload['text'])
        self.assertIn("  - Rua B", payload['text']) # From user3

        # Login list should truncate to user1 and user2
        self.assertIn("Listando alguns clientes:", payload['text'])
        self.assertIn("- *Login:* `user1`", payload['text'])
        self.assertIn("  *Última conexão:* 2023-01-01 10:00", payload['text'])
        self.assertIn("- *Login:* `user2`", payload['text'])
        self.assertIn("  *Última conexão:* 2023-01-01 11:00", payload['text'])
        self.assertNotIn("- *Login:* `user3`", payload['text'])
        self.assertIn("... e mais 1 clientes.", payload['text'])

    @patch('alert_service.alert_service.requests.post')
    def test_telegram_api_failure(self, mock_post):
        clients = [{'login': 'user1', 'ultima_conexao_final': 'today', 'bairro': 'Centro', 'endereco': 'Rua A'}]
        mock_post.side_effect = requests.exceptions.RequestException("Telegram API down")

        result = send_telegram_alert(clients, 'offline', 'TestConnection')

        self.assertEqual(result.get('error'), "Telegram API down")
        self.assertTrue(result.get('error') is not None) # Check if error key exists

if __name__ == '__main__':
    unittest.main()
