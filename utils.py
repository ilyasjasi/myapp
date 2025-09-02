from app import db
from models import AppSetting

def get_setting(key, default_value=None):
    """Get application setting value"""
    setting = AppSetting.query.get(key)
    return setting.value if setting else default_value

def set_setting(key, value):
    """Set application setting value"""
    setting = AppSetting.query.get(key)
    if setting:
        setting.value = value
    else:
        setting = AppSetting(key=key, value=value)
        db.session.add(setting)
    
    db.session.commit()
