from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QDialog, QFileDialog
import os
from .engine_logic import run_engine_process

class EngineDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Run Engine")
        self.resize(400, 150)

        layout = QtWidgets.QVBoxLayout()

        self.input_label = QtWidgets.QLabel("Select Input File:")
        self.input_path = QtWidgets.QLineEdit()
        self.input_button = QtWidgets.QPushButton("Browse...")
        self.input_button.clicked.connect(self.select_input)

        self.run_button = QtWidgets.QPushButton("Run Engine")
        self.run_button.clicked.connect(self.run_engine)

        layout.addWidget(self.input_label)
        layout.addWidget(self.input_path)
        layout.addWidget(self.input_button)
        layout.addWidget(self.run_button)

        self.setLayout(layout)

    def select_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if path:
            self.input_path.setText(path)

    def run_engine(self):
        input_file = self.input_path.text()
        if not os.path.exists(input_file):
            QtWidgets.QMessageBox.warning(self, "Error", "Invalid file path.")
            return
        run_engine_process(input_file)
        QtWidgets.QMessageBox.information(self, "Success", "Engine process completed.")
