from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from ..storage import REPORT_DIR, load_reports


class HistoryDialog(QDialog):
    report_selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("历史检测报告"); self.resize(760,460); self.rows=load_reports(300)
        layout=QVBoxLayout(self); self.search=QLineEdit(); self.search.setPlaceholderText("搜索地区、结论或报告编号"); self.search.textChanged.connect(self.refresh); layout.addWidget(self.search)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(["时间","地区","结论","报告编号"]); self.table.setSelectionBehavior(QTableWidget.SelectRows); layout.addWidget(self.table)
        actions=QHBoxLayout(); open_button=QPushButton("打开"); open_button.clicked.connect(self.open_selected); export=QPushButton("导出"); export.clicked.connect(self.export_selected); delete=QPushButton("删除本地报告"); delete.clicked.connect(self.delete_selected); actions.addWidget(open_button); actions.addWidget(export); actions.addWidget(delete); actions.addStretch(); layout.addLayout(actions); self.refresh()

    def refresh(self):
        query=self.search.text().strip().lower() if hasattr(self,"search") else ""; visible=[r for r in self.rows if query in " ".join(str(r.get(k,"")) for k in ("target_region_id","conclusion","report_id")).lower()]; self.visible=visible; self.table.setRowCount(len(visible))
        for i,row in enumerate(visible):
            for j,value in enumerate((row.get("checked_at",""),row.get("target_region_id",""),row.get("conclusion",""),row.get("report_id",""))): self.table.setItem(i,j,QTableWidgetItem(str(value)))

    def selected(self):
        row=self.table.currentRow(); return self.visible[row] if 0<=row<len(self.visible) else None
    def open_selected(self):
        row=self.selected()
        if row: self.report_selected.emit(row); self.accept()
    def export_selected(self):
        row=self.selected()
        if not row: return
        path,_=QFileDialog.getSaveFileName(self,"导出报告",f"VD-Nexus-{row['report_id']}.json","JSON (*.json)")
        if path: Path(path).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding="utf-8")
    def delete_selected(self):
        row=self.selected()
        if not row or QMessageBox.question(self,"删除报告","只删除本机该份报告，是否继续？")!=QMessageBox.Yes: return
        (REPORT_DIR/f"{row['report_id']}.json").unlink(missing_ok=True); self.rows=[x for x in self.rows if x.get("report_id")!=row.get("report_id")]; self.refresh()
