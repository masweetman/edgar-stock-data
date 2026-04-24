import json
import logging
from datetime import datetime, timezone

from flask import request
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user

from app import db
from app.models import StockDataEntry, User, UserConfig

_audit_logger = logging.getLogger('audit')


def _audit(event: str, user_id=None, extra: dict | None = None) -> None:
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': event,
        'user_id': user_id,
        'ip': request.remote_addr,
        **(extra or {}),
    }
    _audit_logger.info(json.dumps(record))


class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        from flask import redirect, url_for
        return redirect(url_for('main.login'))

    def on_model_change(self, form, model, is_created):
        event = 'admin_create' if is_created else 'admin_update'
        _audit(event, user_id=current_user.id,
               extra={'model': type(model).__name__, 'model_id': getattr(model, 'id', None)})
        super().on_model_change(form, model, is_created)

    def on_model_delete(self, model):
        _audit('admin_delete', user_id=current_user.id,
               extra={'model': type(model).__name__, 'model_id': getattr(model, 'id', None)})
        super().on_model_delete(model)


class UserAdminView(AdminModelView):
    column_exclude_list = ('password_hash', 'two_factor_secret')
    form_excluded_columns = ('password_hash', 'two_factor_secret', 'created_at', 'config', 'stock_data')
    can_create = False


class UserConfigAdminView(AdminModelView):
    pass


class StockDataAdminView(AdminModelView):
    can_create = False
    can_edit = False


def register_admin_views(admin_instance) -> None:
    admin_instance.add_view(UserAdminView(User, db.session, name='Users'))
    admin_instance.add_view(UserConfigAdminView(UserConfig, db.session, name='User Configs'))
    admin_instance.add_view(StockDataAdminView(StockDataEntry, db.session, name='Stock Data'))
