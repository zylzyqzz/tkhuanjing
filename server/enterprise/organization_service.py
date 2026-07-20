from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Customer, LiveRoom
from ..models_enterprise import AnchorProfile, LiveAccount

class OrganizationService:
    """Compatibility facade: Customer is the Phase 0 persistence model for Organization."""
    def __init__(self,db:Session,organization_id:int): self.db=db;self.organization_id=organization_id
    def get(self)->Customer|None:return self.db.get(Customer,self.organization_id)
    def rooms(self):return self.db.scalars(select(LiveRoom).where(LiveRoom.customer_id==self.organization_id,LiveRoom.status=="active").order_by(LiveRoom.name)).all()
    def accounts(self):return self.db.scalars(select(LiveAccount).where(LiveAccount.organization_id==self.organization_id,LiveAccount.status=="active").order_by(LiveAccount.display_name)).all()
    def anchors(self):return self.db.scalars(select(AnchorProfile).where(AnchorProfile.organization_id==self.organization_id,AnchorProfile.status=="active").order_by(AnchorProfile.display_name)).all()
