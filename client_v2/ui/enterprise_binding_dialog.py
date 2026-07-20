from __future__ import annotations
from PySide6.QtWidgets import QComboBox,QDialog,QFormLayout,QLabel,QLineEdit,QMessageBox,QPushButton,QVBoxLayout
from ..api import ClientApi
from ..product import APP_VERSION
from ..storage import load_config,load_credentials,save_credentials

class EnterpriseBindingDialog(QDialog):
 def __init__(self,parent=None):
  super().__init__(parent);self.setWindowTitle("企业与直播间绑定");self.setMinimumWidth(460);self.config=load_config();self.credentials=load_credentials();self.api=ClientApi(self.config["api_base"],self.credentials.get("device_token",""));self.options={}
  root=QVBoxLayout(self);self.status=QLabel("请先登录企业成员账号");self.status.setWordWrap(True);root.addWidget(self.status);form=QFormLayout();root.addLayout(form)
  self.username=QLineEdit();self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password);form.addRow("企业账号",self.username);form.addRow("登录密码",self.password)
  login=QPushButton("登录并同步可绑定资源");login.clicked.connect(self.login);form.addRow("",login)
  self.room=QComboBox();self.account=QComboBox();self.anchor=QComboBox();form.addRow("直播间",self.room);form.addRow("TikTok 账号",self.account);form.addRow("主播",self.anchor)
  bind=QPushButton("确认绑定");bind.setProperty("primary",True);bind.clicked.connect(self.bind);form.addRow("",bind);self.refresh_current()
 def ensure_device(self):
  if not self.api.token:
   x=self.api.register(self.config,APP_VERSION);save_credentials(device_token=x["device_token"]);self.api.token=x["device_token"]
 def refresh_current(self):
  try:
   self.ensure_device();x=self.api.v2_binding();b=x.get("binding");self.status.setText(f"当前绑定：直播间 #{b['room_id']} · 最后同步 {x.get('synced_at','')}" if b else "当前设备尚未绑定企业直播间")
  except Exception:self.status.setText("当前绑定状态暂时无法同步")
 def login(self):
  try:
   x=self.api.enterprise_login(self.username.text().strip(),self.password.text());token=x["token"];save_credentials(organization_member_token=token);self.options=self.api.enterprise_options(token)
   self.room.clear();self.account.clear();self.anchor.clear()
   for row in self.options["rooms"]:self.room.addItem(row["name"],row["id"])
   self.account.addItem("不关联账号",None)
   for row in self.options["accounts"]:self.account.addItem(row["display_name"],row["id"])
   self.anchor.addItem("不关联主播",None)
   for row in self.options["anchors"]:self.anchor.addItem(row["display_name"],row["id"])
   self.status.setText(f"已登录：{self.options['organization']['name']}")
  except Exception as exc:QMessageBox.warning(self,"企业登录失败",str(exc))
 def bind(self):
  token=load_credentials().get("organization_member_token","")
  if not token or self.room.currentData() is None:QMessageBox.warning(self,"无法绑定","请先登录并选择直播间");return
  try:
   x=self.api.v2_bind(token,{"room_id":self.room.currentData(),"account_id":self.account.currentData(),"anchor_id":self.anchor.currentData(),"binding_type":"primary","reason":"客户端绑定"});save_credentials(v2_binding_id=str(x["binding"]["id"]));self.status.setText(f"绑定成功：直播间 #{x['binding']['room_id']}");QMessageBox.information(self,"绑定完成","企业、直播间、账号和主播已同步。")
  except Exception as exc:QMessageBox.warning(self,"绑定冲突或失败",str(exc))
