import datetime
from app.helpers import RegistrationNumberService
from app.models import RegistrationNumberSetting

def test_preview_number_formatting(db):
    test_date = datetime.date(2026, 9, 6)
    preview = RegistrationNumberService.preview_number(
        format_pattern='REG-{YYYY}-{MM}-{NUMBER}',
        next_number=125,
        padding=6,
        ref_date=test_date
    )
    assert preview == 'REG-2026-09-000125'

    preview_yy = RegistrationNumberService.preview_number(
        format_pattern='CLI/{YY}/{DD}/{NUMBER}',
        next_number=42,
        padding=4,
        ref_date=test_date
    )
    assert preview_yy == 'CLI/26/06/0042'

def test_allocate_next_number_advances_counter(db):
    setting = RegistrationNumberSetting.query.first()
    setting.format_pattern = 'PAT-{YYYY}-{NUMBER}'
    setting.next_number = 200
    setting.increment_amount = 5
    setting.padding = 5
    db.session.commit()

    reg_1 = RegistrationNumberService.allocate_next_number()
    curr_year = datetime.date.today().strftime('%Y')
    assert reg_1 == f'PAT-{curr_year}-00200'

    setting_after_1 = RegistrationNumberSetting.query.first()
    assert setting_after_1.next_number == 205

    reg_2 = RegistrationNumberService.allocate_next_number()
    assert reg_2 == f'PAT-{curr_year}-00205'

    setting_after_2 = RegistrationNumberSetting.query.first()
    assert setting_after_2.next_number == 210

def test_allocation_uniqueness(db):
    nums = set()
    for _ in range(10):
        num = RegistrationNumberService.allocate_next_number()
        assert num not in nums
        nums.add(num)
    assert len(nums) == 10

