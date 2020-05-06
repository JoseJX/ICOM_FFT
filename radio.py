#!/usr/bin/python3
import Hamlib
import pyaudio
import threading
import numpy as np
from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QVBoxLayout,QHBoxLayout,QLCDNumber,QPushButton
from PyQt5.QtCore import pyqtSlot
import pyqtgraph as pg


class AudioRecorder(object):
    def __init__(self, pa, dev, rate=8000):
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

        # Set up the audio
        self.setupAudio()

        # Set up the rig
        self.setupRig(311)

        # Set up the UI
        self.setupUI()

        # Set up the data
        self.setupFFT()
        
        # Update the radio frequency from the radio
        self.lcd.display(self.rigFreq)

        # Set up the timer for updating the window and audio
        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        # FIXME: Make user controlled
        timer.start(50)
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
        self.rigFreq = self.rig.get_freq()

    # Set up the UI
    def setupUI(self):
        # Set up the Layout
        vbox = QVBoxLayout()

        # Set up the frequency input
        hbox = QHBoxLayout()
        self.lcd = QLCDNumber(self)
        self.lcd.setDigitCount(10)
        hbox.addWidget(self.lcd)
        lcdVbox = QVBoxLayout()
        self.freqUp = QPushButton("+")
        self.freqUp.clicked.connect(self.doFreqUp)
        self.freqDown = QPushButton("-")
        self.freqDown.clicked.connect(self.doFreqDown)
        lcdVbox.addWidget(self.freqUp)
        lcdVbox.addWidget(self.freqDown)
        hbox.addLayout(lcdVbox)
        vbox.addLayout(hbox)

        # Set up the FFT plotting widget
        self.fft = pg.PlotWidget(name='FFT')
        vbox.addWidget(self.fft)
        self.fftPlot = self.fft.plot()
        self.fftPlot.setPen((255,255,255))
        self.fft.setLabel('bottom', 'Frequency', units='Hz')
        self.fft.setYRange(0, 1.0)
        self.fft.setXRange(0, self.freq.max())

        # Set up the Waterfall plotting widget
        self.waterfall = pg.PlotWidget(name='Waterfall')
        self.waterfall.setLabel('left', 'Time')
        self.waterfallPlot = pg.ImageItem()
        self.waterfall.clear()
        self.waterfall.addItem(self.waterfallPlot)
        vbox.addWidget(self.waterfall)

        # Set the layout and geometry and show the GUI
        self.setLayout(vbox)
        self.setGeometry(0, 0, 800, 600)
        self.setWindowTitle('ICOM IC-706 MKIIG Control and FFT')
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

        # Get the audio frequencies for printing
        self.freq = np.fft.rfftfreq(self.ar.bufSize, 1.0/self.ar.rate)

        # Start recording
        self.ar.start()

    # Set up the initial FFT window
    def setupFFT(self):
        # FFT Data over time
        # FIXME: Make this variable...
        self.fftLineCt = 512
        self.fftData = np.zeros((self.fftLineCt, int(self.ar.bufSize/2) + 1))

    # Change the frequency up
    @pyqtSlot()
    def doFreqUp(self):
       self.rigFreq += 1000 
       self.rig.set_freq(Hamlib.RIG_VFO_A, self.rigFreq)
       self.lcd.display(self.rigFreq)

    # Change the frequency down
    @pyqtSlot()
    def doFreqDown(self):
       self.rigFreq -= 1000 
       self.rig.set_freq(Hamlib.RIG_VFO_A, self.rigFreq)
       self.lcd.display(self.rigFreq)

    # Update the FFT Window and get new data
    def update(self):
        # Get new data
        framesList = self.ar.getFrames()
        toFFT = len(framesList)

        # Make sure we have data to process
        if (toFFT > 0):
            # Convert input data to numpy
            frames = np.empty([toFFT, self.ar.bufSize], dtype=np.float32)
            for i in range(toFFT):
                frames[i,:] = np.frombuffer(framesList[i], dtype=np.int16).astype(np.float32)

            # Computes the FFT
            fftSig = np.abs(np.fft.rfft(frames))
            
            # Normalize
            oneLine = fftSig[0] / fftSig.max()

            # Copy the result into the data array
            self.fftData[toFFT:self.fftLineCt, :] = self.fftData[0:self.fftLineCt-toFFT, :]
            self.fftData[0:toFFT,:] = fftSig

            # Plot the first one as the line data
            self.fftPlot.setData(self.freq, oneLine)

            # Plot the waterfall
            self.waterfallPlot.setImage(np.rot90(self.fftData,3), autoLevels=True, autoRange=False)


app = QtWidgets.QApplication([])
mw = MainWindow()
mw.show()
app.exec_()
