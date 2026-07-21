from __future__ import annotations

from PySide6.QtWidgets import QComboBox,QDialog,QFormLayout,QLabel,QLineEdit,QMessageBox,QPushButton,QVBoxLayout

from ..api import ApiError,ClientApi
from ..product import APP_VERSION
from ..storage import clear_credentials,load_config,load_credentials,save_credentials


class EnterpriseBindingDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle("当前直播间");self.setMinimumWidth(500);self.config=load_config();self.credentials=load_credentials();self.api=ClientApi(self.config["api_base"],self.credentials.get("device_token",""));self.options={};self.current_binding=None
        root=QVBoxLayout(self);title=QLabel("将这台电脑加入企业直播间");title.setProperty("title",True);root.addWidget(title);self.status=QLabel("正在识别本机和当前绑定……");self.status.setWordWrap(True);root.addWidget(self.status);form=QFormLayout();root.addLayout(form)
        self.organization_code=QLineEdit(self.credentials.get("organization_code",""));self.organization_code.setPlaceholderText("例如 ACME-US")
        self.username=QLineEdit(self.credentials.get("organization_username",""));self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password)
        form.addRow("企业代码",self.organization_code);form.addRow("企业账号",self.username);form.addRow("登录密码",self.password)
        login=QPushButton("登录并获取企业配置");login.clicked.connect(self.login);form.addRow("",login)
        self.room=QComboBox();self.account=QComboBox();self.anchor=QComboBox();self.room.currentIndexChanged.connect(self._filter_accounts);form.addRow("目标直播间",self.room);form.addRow("TikTok 账号",self.account);form.addRow("主播",self.anchor)
        self.impact=QLabel("更换后，新的检测和直播数据归属目标直播间；历史数据不会修改。");self.impact.setWordWrap(True);self.impact.setProperty("muted",True);root.addWidget(self.impact)
        bind=QPushButton("确认绑定");bind.setProperty("primary",True);bind.clicked.connect(self.bind);form.addRow("",bind)
        self.unbind_button=QPushButton("解除当前绑定");self.unbind_button.clicked.connect(self.unbind);self.unbind_button.setVisible(False);form.addRow("",self.unbind_button);self.refresh_current()

    def ensure_device(self):
        if not self.api.token:
            value=self.api.register(self.config,APP_VERSION);save_credentials(device_token=value["device_token"]);self.api.token=value["device_token"]

    def refresh_current(self):
        try:
            self.ensure_device();value=self.api.v2_binding();self.current_binding=value.get("binding");self.status.setText("这台电脑已经绑定直播间。登录后可查看详情或更换绑定。" if self.current_binding else "已识别这台电脑，当前尚未绑定企业直播间。");self.unbind_button.setVisible(bool(self.current_binding))
        except Exception:self.status.setText("暂时无法同步当前绑定，请检查网络后重试。")

    def login(self):
        code=self.organization_code.text().strip();username=self.username.text().strip()
        if not code:QMessageBox.warning(self,"需要企业代码","请输入企业管理员提供的企业代码。");return
        try:
            value=self.api.enterprise_login(code,username,self.password.text());token=value["token"];save_credentials(organization_member_token=token,organization_code=code,organization_username=username);self.options=self.api.enterprise_options(token)
            self.room.clear();self.anchor.clear()
            for row in self.options["rooms"]:self.room.addItem(row["name"],row["id"])
            self.anchor.addItem("暂不关联主播",None)
            for row in self.options["anchors"]:self.anchor.addItem(row["display_name"],row["id"])
            self._filter_accounts();self.password.clear();self.status.setText(f"已登录 {self.options['organization']['name']}，请选择这台电脑负责的直播间。")
        except Exception as exc:QMessageBox.warning(self,"企业登录失败",str(exc))

    def _filter_accounts(self):
        current=self.room.currentData();self.account.clear();self.account.addItem("暂不关联账号",None)
        for row in self.options.get("accounts",[]):
            if row.get("room_id") in {None,current}:self.account.addItem(row["display_name"],row["id"])

    def bind(self):
        token=load_credentials().get("organization_member_token","")
        if not token or self.room.currentData() is None:QMessageBox.warning(self,"还不能绑定","请先登录并选择目标直播间。");return
        room_name=self.room.currentText();account_name=self.account.currentText();anchor_name=self.anchor.currentText()
        if self.current_binding:
            message=f"目标绑定：\n{room_name} / {anchor_name} / {account_name}\n\n更换后，新的检测和直播数据归属目标直播间；历史数据不会修改。"
            if QMessageBox.question(self,"确认更换直播间",message,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            value=self.api.v2_bind(token,{"room_id":self.room.currentData(),"account_id":self.account.currentData(),"anchor_id":self.anchor.currentData(),"binding_type":"primary","reason":"客户端确认换绑" if self.current_binding else "客户端首次绑定"});save_credentials(v2_binding_id=str(value["binding"]["id"]));self.current_binding=value["binding"];self.unbind_button.setVisible(True);self.status.setText(f"当前直播间：{room_name} / {anchor_name} / {account_name}");QMessageBox.information(self,"绑定完成",f"绑定成功。\n\n电脑：本机\n直播间：{room_name}\n主播：{anchor_name}\n账号：{account_name}\n\n客户端将在 20 秒内开始同步状态。")
        except Exception as exc:
            if self._session_expired(exc):return
            QMessageBox.warning(self,"绑定未完成",f"{exc}\n\n请确认直播间没有绑定其他主电脑，然后重试。")

    def unbind(self):
        token=load_credentials().get("organization_member_token","")
        if not token:return
        if QMessageBox.warning(self,"确认解除绑定","解除后，这台电脑的新检测数据将不再归属当前直播间；历史数据不会删除。",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:self.api.v2_unbind(token,"客户端确认解绑");self.current_binding=None;self.unbind_button.setVisible(False);self.status.setText("已解除绑定。请重新选择直播间后完成绑定。");QMessageBox.information(self,"已解除绑定","当前绑定已解除，历史数据保持不变。")
        except Exception as exc:
            if self._session_expired(exc):return
            QMessageBox.warning(self,"解除绑定失败",str(exc))

    def _session_expired(self,exc:Exception)->bool:
        if isinstance(exc,ApiError) and (exc.code in {"AUTH_INVALID","AUTH_EXPIRED"} or exc.status_code==401):
            clear_credentials("organization_member_token");self.status.setText("企业登录会话已过期，请重新输入密码登录后继续。")
            QMessageBox.warning(self,"登录已过期","企业登录会话已失效，当前绑定没有改变。请重新登录后继续。")
            return True
        return False
