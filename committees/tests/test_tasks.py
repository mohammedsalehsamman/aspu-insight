from unittest.mock import patch

from django.test import SimpleTestCase

from committees.tasks import check_committee_deadlines


class CheckCommitteeDeadlinesTaskTests(SimpleTestCase):
    @patch('committees.tasks.CommitteeService.expire_overdue_committees')
    def test_task_delegates_to_service(self, mock_expire):
        check_committee_deadlines.run()
        mock_expire.assert_called_once()
