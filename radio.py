import Hamlib
import pyaudio
import threading
import numpy as np
from scipy import signal
from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QVBoxLayout
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure


class AudioRecorder(object):
    def __init__(self, pa, dev, rate=48000):
        self.rate = rate
        self.bufSize = 1024
        self.pa = pa
        self.stream = self.pa.open(format=pyaudio.paInt16, channels=1, rate=self.rate, input=True, stream_callback=self.frame, frames_per_buffer=1024, input_device_index=dev)
        self.lock = threading.Lock()
        self.stop = False
        self.frames = []

    def frame(self, data, count, timeInfo, status):
        with self.lock:
            self.frames.append(data)
            if (self.stop):
                return None, pyaudio.paComplete
        return None, pyaudio.paContinue

    def getFrames(self):
        with self.lock:
            f = self.frames
            self.frames = []
            return f

    def start(self):
        self.stream.start_stream()

    def close(self):
        with self.lock:
            self.stop = True
        self.stream.close()
        self.pa.terminate()

# Main window
class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        QtWidgets.QWidget.__init__(self)

        # Set up the UI
        self.setupUI()

        # Set up the audio
        self.setupAudio()

        # Set up the rig
        self.setupRig(311)

        # Set up the data
        self.setupFFT()
        
        # Set up the timer for updating the window and audio
        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        # FIXME: Make user controlled
        timer.start(100)
        self.timer = timer

    # Get a list of supported models from hamlib
    def getModelMagic():
        return {v for v in iter(dir(Hamlib)) if v.startswith("RIG_MODEL")}

    # Get a list of codes, associated with the models
    def getModelCodes():
        models = getModelMagic()
        codes = { k:Hamlib.__dict__[k] for k in models }
        return codes

    # Set up the rig
    def setupRig(self, rigCode):
        self.rig = Hamlib.Rig(rigCode)
        self.rig.set_conf("rig_pathname", "/dev/ttyUSB0")
        self.rig.set_conf("retry", "5")
        self.rig.open()

    # Set up the UI
    def setupUI(self):
        # Set up the widget
        vbox = QVBoxLayout()
        self.figure = Figure(facecolor='white')
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        vbox.addWidget(self.toolbar)
        vbox.addWidget(self.canvas)
        self.setLayout(vbox)

        self.setGeometry(300, 300, 350, 300)
        self.setWindowTitle('FFT')
        self.show()

    # Set up the audio
    def setupAudio(self):
        # Create the pa instance
        self.pa = pyaudio.PyAudio()
        pd = None
        pn = 0
        print("Input devices:");
        for i in range(self.pa.get_device_count()):
            dev = self.pa.get_device_info_by_index(i)
            if (dev.get('maxInputChannels') > 0):
                print(" ",i, dev['name'])

            # FIXME
            if (dev['name'].startswith("pulse")):
                pd = dev
                pn = i
        self.ar = AudioRecorder(self.pa, pn)

        # Set up the audio data for processing
        self.freq = np.fft.rfftfreq(self.ar.bufSize, 1.0/self.ar.rate)
        self.time = np.arange(self.ar.bufSize, dtype=np.float32) / self.ar.rate * 1000.0

        # Start recording
        self.ar.start()

    # Set up the initial FFT window
    def setupFFT(self):
        # FFT axis markers
        self.fft = self.figure.add_subplot(111)
        self.fft.set_ylim(0, 1)
        self.fft.set_xlim(0, self.freq.max())
        self.fft.set_xlabel(u'frequency (Hz)', fontsize=6)
        # FFT Line data
        self.fftLine = self.fft.plot(self.freq, np.ones_like(self.freq))

    # Update the FFT Window and get new data
    def update(self):
        # Get new data
        framesList = self.ar.getFrames()

        # Convert input data to numpy
        print(len(framesList))
        frames = np.empty([len(framesList), self.ar.bufSize], dtype=np.float32)
        for i in range(len(framesList)):
            frames[i,:] = np.frombuffer(framesList[i], dtype=np.int16).astype(np.float32)

        if len(frames) > 0:
            # Average the frames
            data = np.mean(frames, axis=0)

            # computes and plots the fft signal            
            fftSig = np.fft.rfft(data)
            fftSig /= np.abs(fftSig).max()
            self.fftLine[0].set_data(self.freq, np.abs(fftSig))
            
            # Refresh the plot
            self.canvas.draw()

app = QtWidgets.QApplication([])
mw = MainWindow()
mw.show()
app.exec_()
