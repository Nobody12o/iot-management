import unittest
from unittest.mock import MagicMock, patch

# PASUL CRUCIAL: Păcălim pymysql înainte ca app.py să fie importat!
import sys
import pymysql

# Înlocuim funcția connect cu un mock care returnează un obiect fals (fără conexiune reală)
mock_db = MagicMock()
pymysql.connect = MagicMock(return_value=mock_db)

# Acum putem importa app în siguranță! Nu se va mai bloca la conexiunea de bază de date.
from app import check_for_anomalies

class TestCheckForAnomalies(unittest.TestCase):

    def setUp(self):
        # Pregătim un cursor fictiv pentru a simula răspunsurile bazei de date
        self.mock_cursor = MagicMock()
        
        # Facem patch pe db.cursor() global din app.py ca să returneze cursorul nostru fictiv
        self.patcher_cursor = patch('app.db.cursor', return_value=self.mock_cursor)
        self.patcher_cursor.start()
        
        # Facem patch și pe db.ping() ca să nu dea erori la ping
        self.patcher_ping = patch('app.db.ping')
        self.patcher_ping.start()

    def tearDown(self):
        # Oprim simulările după terminarea fiecărui test
        self.patcher_cursor.stop()
        self.patcher_ping.stop()

    def test_anomaly_critical_high_temp_no_active_alarm(self):
        """Testăm declanșarea unei alarme CRITICE (35°C) când nu există alte alarme active."""
        self.mock_cursor.fetchone.return_value = None

        check_for_anomalies(35.0)

        # Verificăm dacă s-a apelat INSERT pentru alarma critică
        first_call_args = self.mock_cursor.execute.call_args_list[1][0]
        sql_query = first_call_args[0]
        params = first_call_args[1]

        self.assertIn("INSERT INTO ALARMS", sql_query)
        self.assertEqual(params[0], 'critical')
        self.assertIn("Alertă Critică", params[1])

    def test_anomaly_warning_high_temp_no_active_alarm(self):
        """Testăm declanșarea unei alarme de tip WARNING (29°C) când nu există alte alarme active."""
        self.mock_cursor.fetchone.return_value = None

        check_for_anomalies(29.0)

        first_call_args = self.mock_cursor.execute.call_args_list[1][0]
        sql_query = first_call_args[0]
        params = first_call_args[1]

        self.assertIn("INSERT INTO ALARMS", sql_query)
        self.assertEqual(params[0], 'warning')
        self.assertIn("Atenție (Warning)", params[1])

    def test_temperature_returns_to_normal_resolves_active_alarm(self):
        """Testăm dacă o alarmă activă de tip 'ACTIVE' se închide automat când temperatura revine la normal (22°C)."""
        self.mock_cursor.fetchone.side_effect = [
            (10, 'warning', 'ACTIVE'), # Primul fetchone pentru alarma_activa
            ('ACTIVE',)                 # Al doilea fetchone
        ]

        check_for_anomalies(22.0)

        called_queries = [call[0][0] for call in self.mock_cursor.execute.call_args_list]
        update_query_exists = any("UPDATE ALARMS" in q and "status = 'RESOLVED'" in q for q in called_queries)
        self.assertTrue(update_query_exists)

if __name__ == '__main__':
    unittest.main()