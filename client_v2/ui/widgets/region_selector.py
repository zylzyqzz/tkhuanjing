from PySide6.QtWidgets import QComboBox

from ...regions import REGIONS


FLAGS = {"US":"🇺🇸","CA":"🇨🇦","GB":"🇬🇧","DE":"🇩🇪","FR":"🇫🇷","JP":"🇯🇵","KR":"🇰🇷","SG":"🇸🇬","AU":"🇦🇺","CN":"🇨🇳"}


class RegionSelector(QComboBox):
    def __init__(self, selected: str = "", parent=None):
        super().__init__(parent)
        for region in REGIONS:
            self.addItem(f"{FLAGS.get(region.country_code, '🌐')}  {region.label}", region.region_id)
        self.setCurrentIndex(max(0, self.findData(selected)))
        self.setMinimumWidth(330)
