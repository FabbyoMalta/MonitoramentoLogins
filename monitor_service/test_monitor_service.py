import unittest
from unittest.mock import patch, MagicMock, call, ANY
import time
import uuid
import json
import sys
import os

# Ensure the service module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from monitor_service import monitor_service

class TestMonitorService(unittest.TestCase):

    def setUp(self):
        # Reset global states or configurations if necessary
        monitor_service.eventos_ativos = []
        monitor_service.THRESHOLD_OFFLINE_CLIENTS = 2 # Lower for easier testing
        
        # Mock external services and time
        self.mock_requests_get = patch('requests.get').start()
        self.mock_requests_post = patch('requests.post').start()
        self.mock_time = patch('time.time').start()
        self.mock_uuid = patch('uuid.uuid4').start()
        self.mock_sleep = patch('time.sleep').start() # To prevent actual sleeping

        # Mock database
        self.mock_sqlite_connect = patch('sqlite3.connect').start()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_sqlite_connect.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor
        
        # Default mock values
        self.mock_time.return_value = 1000.0
        self.mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
        self.mock_requests_get.return_value.json.return_value = {'clientes': []} # Default to no clients
        self.mock_requests_post.return_value.json.return_value = {"motivo_final": "mock_olt_reason"}
        self.mock_requests_post.return_value.raise_for_status = MagicMock()

        # Initialize DB (in-memory for tests if not already handled by mocks)
        # monitor_service.init_db() # This would use the mocked connect

    def tearDown(self):
        patch.stopall()

    def _run_monitor_cycle(self, num_cycles=1):
        """Helper to run the monitor_connections loop a few times."""
        # This is tricky because of the while True loop.
        # We'll make time.sleep raise an exception after N calls to break the loop.
        side_effects = [None] * num_cycles + [KeyboardInterrupt] 
        self.mock_sleep.side_effect = side_effects
        try:
            monitor_service.monitor_connections()
        except KeyboardInterrupt:
            pass # Expected way to stop the loop in this test setup

    def _get_mock_clients(self, logins, conexao_name="CONEXAO_A", id_transmissor="OLT1"):
        return [{'login': l, 'conexao': conexao_name, 'id_transmissor': id_transmissor} for l in logins]

    # 1. New Event Creation
    def test_new_event_creation(self):
        self.mock_time.return_value = 1000.0
        event_id = uuid.UUID('11111111-1111-1111-1111-111111111111')
        self.mock_uuid.return_value = event_id

        offline_clients_data = self._get_mock_clients(['client1', 'client2', 'client3'], conexao_name="CONEXAO_NEW")
        
        # First cycle: no clients (initial state)
        # Second cycle: clients go offline
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online clients (empty)
            MagicMock(json=MagicMock(return_value={'clientes': []})), # offline clients (empty) - initial state
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online clients (empty) 
            MagicMock(json=MagicMock(return_value={'clientes': offline_clients_data})), # offline clients
        ]

        self._run_monitor_cycle(num_cycles=2)

        # Verify save_event call for the new event
        expected_event_data = {
            'id': str(event_id),
            'conexao': 'CONEXAO_NEW',
            'logins_offline': {'client1', 'client2', 'client3'},
            'logins_restantes': {'client1', 'client2', 'client3'},
            'timestamp': 1000.0 
        }
        # The actual call to save_event includes the event object and status
        # We need to ensure the first argument to save_event matches our expected_event_data structure
        args, kwargs = self.mock_cursor.execute.call_args_list[-1] # Assuming last execute is the save
        
        # Example: INSERT OR REPLACE INTO events (id, conexao, timestamp, status, logins) VALUES (?, ?, ?, ?, ?)
        # args[1] would be the tuple of values
        saved_values = args[1]
        self.assertEqual(saved_values[0], str(event_id))
        self.assertEqual(saved_values[1], 'CONEXAO_NEW')
        self.assertEqual(saved_values[2], 1000.0) # Timestamp
        self.assertEqual(saved_values[3], "ativo") # Status
        self.assertEqual(set(json.loads(saved_values[4])), {'client1', 'client2', 'client3'})


        # Verify alerts
        self.mock_requests_post.assert_any_call(
            f"{monitor_service.ALERT_SERVICE_URL}/alerta/telegram",
            json={
                'clientes': offline_clients_data, 
                'status': 'offline', 
                'conexao': 'CONEXAO_NEW',
                'mensagem_personalizada': ANY # Check for specific message if important
            }
        )
        self.mock_requests_post.assert_any_call(
            f"{monitor_service.ALERT_SERVICE_URL}/alerta/whatsapp",
            json={
                'total_clientes': 3, 
                'conexao': 'CONEXAO_NEW', 
                'motivo': 'mock_olt_reason'
            }
        )
        self.assertEqual(len(monitor_service.eventos_ativos), 1)
        self.assertEqual(monitor_service.eventos_ativos[0]['id'], str(event_id))


    # 2. Adding Clients to Existing Event & 3. Event Timestamp Preservation
    def test_adding_clients_to_existing_event_and_timestamp_preservation(self):
        initial_timestamp = 1000.0
        self.mock_time.return_value = initial_timestamp # Initial event creation time
        
        existing_event_id = uuid.UUID('22222222-2222-2222-2222-222222222222')
        self.mock_uuid.return_value = existing_event_id

        initial_offline_clients = self._get_mock_clients(['clientA', 'clientB'], conexao_name="CONEXAO_EXISTING")
        
        # Simulate initial event creation in DB and memory
        monitor_service.eventos_ativos = [{
            'id': str(existing_event_id),
            'conexao': 'CONEXAO_EXISTING',
            'logins_offline': {'clientA', 'clientB'},
            'logins_restantes': {'clientA', 'clientB'},
            'timestamp': initial_timestamp
        }]
        # Mock DB to show this event as active
        self.mock_cursor.fetchone.return_value = (1,) # For existe_evento_ativo_para_conexao
        # Mock carregar_eventos_ativos to load this event (though we set it directly for simplicity here)
        self.mock_cursor.fetchall.return_value = [
            (str(existing_event_id), "CONEXAO_EXISTING", initial_timestamp, "ativo", json.dumps(['clientA', 'clientB']))
        ]


        # New clients going offline for the SAME connection
        newly_offline_clients_data = self._get_mock_clients(['clientC', 'clientD'], conexao_name="CONEXAO_EXISTING")

        # Simulate time passing for the update
        update_time = 1500.0
        self.mock_time.return_value = update_time

        # API calls:
        # 1. Initial load (empty previous state)
        #    - get_clients('offline') -> []
        #    - get_clients('online') -> []
        # 2. Cycle where new clients appear
        #    - get_clients('offline') -> initial_offline_clients + newly_offline_clients_data
        #    - get_clients('online') -> []
        
        # We need to adjust mock_requests_get for the sequence of calls in monitor_connections
        # Setup initial state (clientes_offline_anterior)
        monitor_service.clientes_offline_anterior = {'clientA', 'clientB'}
        monitor_service.clientes_info_offline_anterior = {
            'clientA': initial_offline_clients[0],
            'clientB': initial_offline_clients[1]
        }
        
        all_offline_now = initial_offline_clients + newly_offline_clients_data
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': all_offline_now })), # offline clients
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online clients
        ]
        
        # We also need existe_evento_ativo_para_conexao to return True for "CONEXAO_EXISTING"
        # This is tricky because existe_evento_ativo_para_conexao is called with its own DB connection
        # For now, let's assume the global `eventos_ativos` is primarily used after initial load,
        # or we mock `existe_evento_ativo_para_conexao` directly.
        with patch('monitor_service.monitor_service.existe_evento_ativo_para_conexao') as mock_existe_evento:
            mock_existe_evento.return_value = True # For "CONEXAO_EXISTING"

            self._run_monitor_cycle(num_cycles=1) # Run one cycle for the update

            # Verify save_event was called with existing ID, updated logins, ORIGINAL timestamp
            # The last call to execute on the cursor should be the save_event for the update
            args, _ = self.mock_cursor.execute.call_args_list[-1]
            saved_values = args[1] # Tuple of values from INSERT OR REPLACE

            self.assertEqual(saved_values[0], str(existing_event_id)) # Existing ID
            self.assertEqual(saved_values[1], "CONEXAO_EXISTING")
            self.assertEqual(saved_values[2], initial_timestamp) # CRUCIAL: Original timestamp
            self.assertEqual(saved_values[3], "ativo") # Status
            self.assertEqual(set(json.loads(saved_values[4])), {'clientA', 'clientB', 'clientC', 'clientD'}) # Updated logins

            # Verify in-memory event is updated
            self.assertEqual(len(monitor_service.eventos_ativos), 1)
            updated_event_in_memory = monitor_service.eventos_ativos[0]
            self.assertEqual(updated_event_in_memory['id'], str(existing_event_id))
            self.assertEqual(updated_event_in_memory['logins_offline'], {'clientA', 'clientB', 'clientC', 'clientD'})
            self.assertEqual(updated_event_in_memory['logins_restantes'], {'clientA', 'clientB', 'clientC', 'clientD'})
            self.assertEqual(updated_event_in_memory['timestamp'], initial_timestamp)

            # Verify alerts for update
            expected_telegram_message = (
                f"เพิ่มเติม {len(newly_offline_clients_data)} clientes offline detectados na conexão CONEXAO_EXISTING. "
                f"Total offline agora: {len(updated_event_in_memory['logins_restantes'])}."
            )
            self.mock_requests_post.assert_any_call(
                f"{monitor_service.ALERT_SERVICE_URL}/alerta/telegram",
                json={
                    'clientes': newly_offline_clients_data, # Only new clients in this alert
                    'status': 'offline', 
                    'conexao': 'CONEXAO_EXISTING',
                    'mensagem_personalizada': expected_telegram_message
                }
            )
            self.mock_requests_post.assert_any_call(
                f"{monitor_service.ALERT_SERVICE_URL}/alerta/whatsapp",
                json={
                    'total_clientes': 4, 
                    'conexao': 'CONEXAO_EXISTING', 
                    'motivo': "Atualização de evento"
                }
            )

    # 4. Event Resolution with Incremental Additions
    @patch('monitor_service.monitor_service.update_event_status') # Mock this specific DB function
    def test_event_resolution_after_incremental_additions(self, mock_update_event_status):
        initial_timestamp = 2000.0
        self.mock_time.return_value = initial_timestamp
        event_id = uuid.UUID('33333333-3333-3333-3333-333333333333')
        self.mock_uuid.return_value = event_id
        conexao_name = "CONEXAO_RESOLVE"

        # Phase 1: Initial clients go offline
        clients_batch1_data = self._get_mock_clients(['user1', 'user2'], conexao_name=conexao_name)
        monitor_service.clientes_offline_anterior = set()
        monitor_service.clientes_info_offline_anterior = {}
        
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': clients_batch1_data})), # offline
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online
        ]
        with patch('monitor_service.monitor_service.existe_evento_ativo_para_conexao', return_value=False):
             self._run_monitor_cycle(num_cycles=1)
        
        self.assertEqual(len(monitor_service.eventos_ativos), 1)
        created_event = monitor_service.eventos_ativos[0]
        self.assertEqual(created_event['logins_offline'], {'user1', 'user2'})

        # Phase 2: More clients go offline on the same connection
        clients_batch2_data = self._get_mock_clients(['user3'], conexao_name=conexao_name)
        monitor_service.clientes_offline_anterior = {'user1', 'user2'} # State after phase 1
        monitor_service.clientes_info_offline_anterior = {
            'user1': clients_batch1_data[0], 'user2': clients_batch1_data[1]
        }
        
        all_currently_offline = clients_batch1_data + clients_batch2_data
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': all_currently_offline})), # offline
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online
        ]
        with patch('monitor_service.monitor_service.existe_evento_ativo_para_conexao', return_value=True):
            self._run_monitor_cycle(num_cycles=1)

        self.assertEqual(len(monitor_service.eventos_ativos), 1)
        updated_event = monitor_service.eventos_ativos[0]
        self.assertEqual(updated_event['logins_offline'], {'user1', 'user2', 'user3'})
        self.assertEqual(updated_event['logins_restantes'], {'user1', 'user2', 'user3'})

        # Phase 3: All clients come back online
        monitor_service.clientes_offline_anterior = {'user1', 'user2', 'user3'}
        monitor_service.clientes_info_offline_anterior = { # Simulate info for all of them
             'user1': all_currently_offline[0], 'user2': all_currently_offline[1], 'user3': all_currently_offline[2]
        }
        # Now, offline clients are empty, online clients contain the resolved ones
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': []})), # offline (all resolved)
            MagicMock(json=MagicMock(return_value={'clientes': all_currently_offline})), # online
        ]
        self._run_monitor_cycle(num_cycles=1)

        # Verify event is resolved and removed
        self.assertEqual(len(monitor_service.eventos_ativos), 0)
        mock_update_event_status.assert_called_once_with(str(event_id), "resolvido")

        # Verify "online" alert
        self.mock_requests_post.assert_any_call(
            f"{monitor_service.ALERT_SERVICE_URL}/alerta/telegram",
            json={
                'clientes': ANY, # Should be a list of dicts for user1, user2, user3
                'status': 'online', 
                'conexao': conexao_name,
                'mensagem_personalizada': None
            }
        )
        # Check that the 'clientes' field in the online alert contains all original offline clients
        found_online_alert = False
        for call_args in self.mock_requests_post.call_args_list:
            url = call_args[0][0]
            if url.endswith("/alerta/telegram"):
                payload = call_args[1]['json']
                if payload['status'] == 'online' and payload['conexao'] == conexao_name:
                    found_online_alert = True
                    alerted_logins = {c['login'] for c in payload['clientes']}
                    self.assertEqual(alerted_logins, {'user1', 'user2', 'user3'})
                    break
        self.assertTrue(found_online_alert, "Online alert for resolved event not found or incorrect.")


    # 5. No Action for Insufficient Clients (New Event)
    def test_no_action_insufficient_clients_new_event(self):
        monitor_service.THRESHOLD_OFFLINE_CLIENTS = 3 # Set higher for this test
        offline_clients_data = self._get_mock_clients(['clientX'], conexao_name="CONEXAO_FEW") # Only 1 client

        monitor_service.clientes_offline_anterior = set()
        monitor_service.clientes_info_offline_anterior = {}
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': offline_clients_data})), # offline
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online
        ]
        
        # Mock `existe_evento_ativo_para_conexao` to always return False as no event should exist yet.
        with patch('monitor_service.monitor_service.existe_evento_ativo_para_conexao', return_value=False):
            self._run_monitor_cycle(num_cycles=1)

        self.assertEqual(len(monitor_service.eventos_ativos), 0) # No event created
        
        # Check that save_event was NOT called (or at least not for this scenario)
        # This is a bit tricky as save_event might be called by other tests if run in same suite instance
        # A more precise way is to count calls before/after or check specific args
        # For simplicity, we check that no new event was added to eventos_ativos.
        # We also check that no alerts for "CONEXAO_FEW" were sent.
        for call_item in self.mock_requests_post.call_args_list:
            payload = call_item[1].get('json', {})
            self.assertNotEqual(payload.get('conexao'), "CONEXAO_FEW", "Alert sent for insufficient clients")


    # 5b. Adding Insufficient New Clients to Existing Event (Still adds them)
    def test_add_insufficient_new_clients_to_existing_event(self):
        monitor_service.THRESHOLD_OFFLINE_CLIENTS = 3 # For new event creation
        initial_timestamp = 3000.0
        self.mock_time.return_value = initial_timestamp
        
        existing_event_id = uuid.UUID('44444444-4444-4444-4444-444444444444')
        # Initial event (already above threshold)
        initial_event_clients = self._get_mock_clients(['BigClient1', 'BigClient2', 'BigClient3'], conexao_name="CONEXAO_ADD_FEW")
        
        monitor_service.eventos_ativos = [{
            'id': str(existing_event_id),
            'conexao': 'CONEXAO_ADD_FEW',
            'logins_offline': {'BigClient1', 'BigClient2', 'BigClient3'},
            'logins_restantes': {'BigClient1', 'BigClient2', 'BigClient3'},
            'timestamp': initial_timestamp
        }]
        monitor_service.clientes_offline_anterior = {'BigClient1', 'BigClient2', 'BigClient3'}
        monitor_service.clientes_info_offline_anterior = {c['login']: c for c in initial_event_clients}

        # New clients go offline for the SAME connection, but this new batch is small (1 client)
        # This batch ITSELF is below threshold, but should still be added to the existing event.
        newly_offline_clients_data = self._get_mock_clients(['SmallClient1'], conexao_name="CONEXAO_ADD_FEW")

        update_time = 3500.0
        self.mock_time.return_value = update_time

        all_offline_now = initial_event_clients + newly_offline_clients_data
        self.mock_requests_get.side_effect = [
            MagicMock(json=MagicMock(return_value={'clientes': all_offline_now})), # offline clients
            MagicMock(json=MagicMock(return_value={'clientes': []})), # online clients
        ]
        
        with patch('monitor_service.monitor_service.existe_evento_ativo_para_conexao', return_value=True):
            self._run_monitor_cycle(num_cycles=1)

            self.assertEqual(len(monitor_service.eventos_ativos), 1)
            updated_event_in_memory = monitor_service.eventos_ativos[0]
            self.assertEqual(updated_event_in_memory['logins_offline'], {'BigClient1', 'BigClient2', 'BigClient3', 'SmallClient1'})
            self.assertEqual(updated_event_in_memory['logins_restantes'], {'BigClient1', 'BigClient2', 'BigClient3', 'SmallClient1'})
            
            # Verify save_event was called for the update
            args, _ = self.mock_cursor.execute.call_args_list[-1]
            saved_values = args[1]
            self.assertEqual(saved_values[0], str(existing_event_id))
            self.assertEqual(set(json.loads(saved_values[4])), {'BigClient1', 'BigClient2', 'BigClient3', 'SmallClient1'})

            # Verify alerts for update (even if the new batch was small)
            expected_telegram_message = (
                f"เพิ่มเติม {len(newly_offline_clients_data)} clientes offline detectados na conexão CONEXAO_ADD_FEW. "
                f"Total offline agora: {len(updated_event_in_memory['logins_restantes'])}."
            )
            self.mock_requests_post.assert_any_call(
                f"{monitor_service.ALERT_SERVICE_URL}/alerta/telegram",
                json={
                    'clientes': newly_offline_clients_data,
                    'status': 'offline', 
                    'conexao': 'CONEXAO_ADD_FEW',
                    'mensagem_personalizada': expected_telegram_message
                }
            )

if __name__ == '__main__':
    # Important: Ensure the CWD is the root of the project for imports to work correctly if run directly
    # For example, if test_monitor_service.py is in monitor_service/tests/
    # and monitor_service.py is in monitor_service/
    # you might need to run from the directory containing the monitor_service package.
    # The sys.path modification at the top helps, but running with `python -m unittest discover`
    # from the project root is generally more robust.
    
    # If you place this test file inside the 'monitor_service' directory alongside 'monitor_service.py':
    # And run from the parent directory of 'monitor_service':
    # python -m unittest monitor_service.test_monitor_service
    unittest.main()

```
