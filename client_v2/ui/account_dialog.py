from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ..api import ClientApi
from ..storage import clear_user_session, load_config, load_user, set_user_session


class AccountDialog(QDialog):
    session_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("账号中心"); self.setFixedSize(520, 430); self.config = load_config(); self.api = ClientApi(self.config["api_base"])
        layout = QVBoxLayout(self); self.status = QLabel(); layout.addWidget(self.status); self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        self.tabs.addTab(self._login_tab(), "登录"); self.tabs.addTab(self._register_tab(), "注册"); self.tabs.addTab(self._reset_tab(), "重置密码"); self.tabs.addTab(self._profile_tab(), "个人资料"); self.refresh()

    def _field(self, password=False):
        field = QLineEdit(); field.setEchoMode(QLineEdit.Password if password else QLineEdit.Normal); return field

    def _login_tab(self):
        page=QWidget(); form=QFormLayout(page); self.login_phone=self._field(); self.login_password=self._field(True); form.addRow("手机号",self.login_phone); form.addRow("密码",self.login_password); button=QPushButton("登录"); button.setProperty("primary",True); button.clicked.connect(self.login); form.addRow("",button); logout=QPushButton("退出登录"); logout.clicked.connect(self.logout); form.addRow("",logout); return page

    def _register_tab(self):
        page=QWidget(); form=QFormLayout(page); self.reg_phone=self._field(); self.reg_email=self._field(); self.reg_code=self._field(); self.reg_password=self._field(True); self.reg_confirm=self._field(True)
        for label, field in (("手机号",self.reg_phone),("邮箱",self.reg_email),("验证码",self.reg_code),("密码",self.reg_password),("确认密码",self.reg_confirm)): form.addRow(label,field)
        row=QHBoxLayout(); self.send_button=QPushButton("发送验证码"); self.send_button.clicked.connect(self.send_register_code); submit=QPushButton("注册"); submit.setProperty("primary",True); submit.clicked.connect(self.register); row.addWidget(self.send_button); row.addWidget(submit); form.addRow("",row); return page

    def _reset_tab(self):
        page=QWidget(); form=QFormLayout(page); self.reset_phone=self._field(); self.reset_code=self._field(); self.reset_new_password=self._field(True); self.reset_confirm=self._field(True)
        for label, field in (("手机号",self.reset_phone),("验证码",self.reset_code),("新密码",self.reset_new_password),("确认密码",self.reset_confirm)): form.addRow(label,field)
        send=QPushButton("发送重置验证码"); send.clicked.connect(self.send_reset_code); submit=QPushButton("重置密码"); submit.clicked.connect(self.submit_reset); form.addRow("",send); form.addRow("",submit); return page

    def _profile_tab(self):
        page=QWidget(); form=QFormLayout(page); self.company=self._field(); self.country=self._field(); self.city=self._field(); self.wechat=self._field()
        for label, field in (("公司",self.company),("国家/地区",self.country),("城市",self.city),("微信",self.wechat)): form.addRow(label,field)
        save=QPushButton("保存资料"); save.setProperty("primary",True); save.clicked.connect(self.save_profile); form.addRow("",save); return page

    def refresh(self):
        user=load_user(); profile=user.get("profile",{}); self.status.setText("已登录："+str(profile.get("phone", "")) if user.get("logged_in") else "当前未登录")
        for key, field in (("company_name",self.company),("country",self.country),("city",self.city),("wechat_id",self.wechat)): field.setText(str(profile.get(key) or ""))

    def _handle(self, action):
        try: return action()
        except Exception as exc: QMessageBox.warning(self,"操作未完成",str(exc)); return None

    def login(self):
        data=self._handle(lambda:self.api.auth_login(self.login_phone.text().strip(),self.login_password.text()))
        if data:
            self.api.token=data["token"]; profile=self._handle(self.api.get_user_profile) or data.get("user",{}); set_user_session(data["token"],profile); self.login_password.clear(); self.refresh(); self.session_changed.emit(load_user())

    def logout(self): clear_user_session(); self.refresh(); self.session_changed.emit(load_user())
    def send_register_code(self):
        if self._handle(lambda:self.api.auth_send_code(self.reg_email.text().strip(),"register")) is not None: self._cooldown(self.send_button)
    def send_reset_code(self): self._handle(lambda:self.api.auth_forgot_password(self.reset_phone.text().strip()))
    def register(self):
        if self.reg_password.text()!=self.reg_confirm.text(): QMessageBox.warning(self,"注册失败","两次密码不一致"); return
        data=self._handle(lambda:self.api.auth_register(self.reg_phone.text().strip(),"CN",self.reg_password.text(),self.reg_email.text().strip(),self.reg_code.text().strip()))
        if data: set_user_session(data["token"],data.get("user",{})); self.refresh(); self.session_changed.emit(load_user())
    def submit_reset(self):
        if self.reset_new_password.text()!=self.reset_confirm.text(): QMessageBox.warning(self,"重置失败","两次密码不一致"); return
        if self._handle(lambda:self.api.auth_reset_password(self.reset_phone.text().strip(),self.reset_code.text().strip(),self.reset_new_password.text())) is not None: clear_user_session(); self.refresh(); self.session_changed.emit(load_user()); QMessageBox.information(self,"重置完成","请使用新密码登录")
    def save_profile(self):
        user=load_user()
        if not user.get("token"): QMessageBox.warning(self,"未登录","请先登录"); return
        self.api.token=user["token"]; data=self._handle(lambda:self.api.update_user_profile(company_name=self.company.text(),country=self.country.text(),city=self.city.text(),wechat_id=self.wechat.text()))
        if data: profile=data.get("profile",data); set_user_session(user["token"],profile); self.refresh(); self.session_changed.emit(load_user())
    def _cooldown(self, button):
        button.setEnabled(False); remaining={"value":60}
        timer=QTimer(button)
        def tick():
            remaining["value"]-=1; button.setText(f"{remaining['value']} 秒后可重发")
            if remaining["value"]<=0: timer.stop(); button.setEnabled(True); button.setText("发送验证码")
        timer.timeout.connect(tick); timer.start(1000)
