// Minimal Socket.IO client test for ASR streaming
const { io } = require('socket.io-client');

const WS_URL = process.env.WS_URL || 'ws://localhost:8087/socket.io';
const serviceId = process.env.ASR_SERVICE_ID || 'vakyansh-asr-en';
const language = process.env.ASR_LANG || 'en';
const samplingRate = Number(process.env.ASR_SR || 16000);

console.log('Connecting to', `${WS_URL}?serviceId=${serviceId}&language=${language}&samplingRate=${samplingRate}`);

const socket = io(WS_URL, {
  transports: ['websocket'],
  query: {
    serviceId,
    language,
    samplingRate: String(samplingRate),
  },
});

const timeout = setTimeout(() => {
  console.error('Timed out waiting for server response');
  socket.disconnect();
  process.exit(1);
}, 10000);

socket.on('connect', () => {
  console.log('Connected. Emitting start...');
  socket.emit('start', { serviceId, language, samplingRate });
});

socket.on('ready', (msg) => {
  console.log('Server ready:', msg);
  clearTimeout(timeout);
  // End test after ready since this is a connectivity check
  socket.disconnect();
});

socket.on('response', (msg) => {
  console.log('Response:', msg);
});

socket.on('error', (err) => {
  console.error('Stream error:', err);
  clearTimeout(timeout);
  socket.disconnect();
  process.exit(2);
});

socket.on('connect_error', (err) => {
  console.error('Connect error:', err.message);
});

socket.on('disconnect', (reason) => {
  console.log('Disconnected:', reason);
  clearTimeout(timeout);
  process.exit(0);
});


