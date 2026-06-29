from celery import shared_task
from committees.services import CommitteeService


@shared_task
def check_committee_deadlines():
    CommitteeService.expire_overdue_committees()
