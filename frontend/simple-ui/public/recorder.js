/*
 * Recorder.js - A JavaScript library for recording audio
 * https://github.com/mattdiamond/Recorderjs
 * 
 * This is a simplified version for the Simple UI application
 */

(function(window) {
  'use strict';

  var Recorder = function(source, cfg) {
    var config = cfg || {};
    var bufferLen = config.bufferLen || 4096;
    var numChannels = config.numChannels || 2;
    var mimeType = config.mimeType || 'audio/wav';
    
    this.context = source.context;
    this.node = (this.context.createScriptProcessor ||
                 this.context.createJavaScriptNode).call(this.context, bufferLen, numChannels, numChannels);
    
    var worker = new Worker(window.URL.createObjectURL(new Blob(["\
      var recLength = 0, recBuffers = [], sampleRate;\
      function init(config) {\
        sampleRate = config.sampleRate;\
      }\
      function record(inputBuffer) {\
        recBuffers.push(inputBuffer.slice(0));\
        recLength += inputBuffer[0].length;\
      }\
      function exportWAV(type) {\
        var buffer = mergeBuffers(recBuffers, recLength);\
        var dataview = encodeWAV(buffer, sampleRate);\
        var blob = new Blob([dataview], { type: type });\
        self.postMessage({command: 'exportWAV', data: blob});\
      }\
      function getBuffer() {\
        var buffers = [];\
        for (var channel = 0; channel < numChannels; channel++) {\
          buffers.push(mergeBuffers(recBuffers, recLength, channel));\
        }\
        self.postMessage({command: 'getBuffer', data: buffers});\
      }\
      function clear() {\
        recLength = 0;\
        recBuffers = [];\
      }\
      function mergeBuffers(recBuffers, recLength, channel) {\
        var result = new Float32Array(recLength);\
        var offset = 0;\
        for (var i = 0; i < recBuffers.length; i++) {\
          result.set(recBuffers[i][channel || 0], offset);\
          offset += recBuffers[i][channel || 0].length;\
        }\
        return result;\
      }\
      function encodeWAV(samples, sampleRate) {\
        var buffer = new ArrayBuffer(44 + samples.length * 2);\
        var view = new DataView(buffer);\
        var writeString = function(string) {\
          for (var i = 0; i < string.length; i++) {\
            view.setUint8(i, string.charCodeAt(i));\
          }\
        }\
        var offset = 0;\
        writeString('RIFF');\
        view.setUint32(offset += 4, 36 + samples.length * 2, true);\
        offset += 4;\
        writeString('WAVE');\
        offset += 4;\
        writeString('fmt ');\
        view.setUint32(offset += 4, 16, true);\
        offset += 4;\
        view.setUint16(offset += 4, 1, true);\
        offset += 2;\
        view.setUint16(offset += 2, 1, true);\
        offset += 2;\
        view.setUint32(offset += 4, sampleRate, true);\
        offset += 4;\
        view.setUint32(offset += 4, sampleRate * 2, true);\
        offset += 4;\
        view.setUint16(offset += 4, 2, true);\
        offset += 2;\
        view.setUint16(offset += 2, 16, true);\
        offset += 2;\
        writeString('data');\
        view.setUint32(offset += 4, samples.length * 2, true);\
        offset += 4;\
        var lng = samples.length;\
        var index = offset;\
        for (var i = 0; i < lng; i++) {\
          view.setInt16(index, samples[i] < 0 ? samples[i] * 0x8000 : samples[i] * 0x7FFF, true);\
          index += 2;\
        }\
        return buffer;\
      }\
      self.onmessage = function(e) {\
        switch(e.data.command) {\
          case 'init':\
            init(e.data.config);\
            break;\
          case 'record':\
            record(e.data.buffer);\
            break;\
          case 'exportWAV':\
            exportWAV(e.data.type);\
            break;\
          case 'getBuffer':\
            getBuffer();\
            break;\
          case 'clear':\
            clear();\
            break;\
        }\
      };\
    "], {type: 'application/javascript'})));
    
    var recording = false;
    var currCallback;
    
    this.node.onaudioprocess = function(e) {
      if (!recording) return;
      var buffer = [];
      for (var channel = 0; channel < numChannels; channel++) {
        buffer.push(e.inputBuffer.getChannelData(channel));
      }
      worker.postMessage({
        command: 'record',
        buffer: buffer
      });
    };
    
    this.configure = function(cfg) {
      for (var prop in cfg) {
        if (cfg.hasOwnProperty(prop)) {
          config[prop] = cfg[prop];
        }
      }
    };
    
    this.record = function() {
      recording = true;
    };
    
    this.stop = function() {
      recording = false;
    };
    
    this.clear = function() {
      worker.postMessage({ command: 'clear' });
    };
    
    this.getBuffer = function(cb) {
      currCallback = cb || config.callback;
      worker.postMessage({ command: 'getBuffer' });
    };
    
    this.exportWAV = function(cb, mimeType, sampleRate) {
      currCallback = cb || config.callback;
      mimeType = mimeType || config.mimeType || 'audio/wav';
      sampleRate = sampleRate || config.sampleRate || 16000;
      worker.postMessage({
        command: 'exportWAV',
        type: mimeType,
        sampleRate: sampleRate
      });
    };
    
    worker.onmessage = function(e) {
      var blob = e.data;
      currCallback(blob);
    };
    
    worker.postMessage({
      command: 'init',
      config: {
        sampleRate: this.context.sampleRate,
        numChannels: numChannels
      }
    });
    
    source.connect(this.node);
    this.node.connect(this.context.destination);
  };
  
  Recorder.forceDownload = function(blob, filename) {
    var url = (window.URL || window.webkitURL).createObjectURL(blob);
    var link = window.document.createElement('a');
    link.href = url;
    link.download = filename || 'recording.wav';
    var click = document.createEvent("Event");
    click.initEvent("click", true, true);
    link.dispatchEvent(click);
  };
  
  window.Recorder = Recorder;
})(window);
