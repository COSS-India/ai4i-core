"""
Integration tests for WebSocket streaming functionality (ASR and TTS).
"""
import pytest
import socketio
import asyncio
from typing import List, Dict, Any


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.streaming
class TestASRStreaming:
    """Test class for ASR WebSocket streaming tests."""

    async def test_asr_streaming_connection(self, test_api_key: str):
        """Test ASR streaming WebSocket connection."""
        sio = socketio.AsyncClient()
        
        try:
            await sio.connect(
                f'http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000&apiKey={test_api_key}'
            )
            assert sio.connected
        finally:
            await sio.disconnect()

    async def test_asr_streaming_connection_without_api_key(self):
        """Test ASR streaming connection without API key."""
        sio = socketio.AsyncClient()
        
        try:
            # This should either connect and then get rejected, or fail to connect
            await sio.connect(
                'http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000'
            )
            # If it connects, it should emit an error event
            await asyncio.sleep(1)  # Wait for potential error event
        except Exception:
            # Connection failure is also acceptable
            pass
        finally:
            if sio.connected:
                await sio.disconnect()

    async def test_asr_streaming_start_event(self, test_api_key: str):
        """Test ASR streaming start event."""
        sio = socketio.AsyncClient()
        ready_received = False
        
        @sio.event
        async def ready():
            nonlocal ready_received
            ready_received = True
        
        try:
            await sio.connect(
                f'http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(1)  # Wait for ready event
            
            assert ready_received
        finally:
            await sio.disconnect()

    async def test_asr_streaming_audio_data(self, test_api_key: str, sample_audio_chunks: List[str]):
        """Test ASR streaming with audio data."""
        sio = socketio.AsyncClient()
        responses_received = []
        
        @sio.event
        async def response(data):
            responses_received.append(data)
        
        try:
            await sio.connect(
                f'http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(0.5)  # Wait for ready
            
            # Send audio chunks
            for i, chunk in enumerate(sample_audio_chunks):
                await sio.emit('data', {
                    'audioData': chunk,
                    'isSpeaking': i < len(sample_audio_chunks) - 1,
                    'disconnectStream': False
                })
                await asyncio.sleep(0.1)  # Small delay between chunks
            
            # Send final chunk
            await sio.emit('data', {
                'audioData': sample_audio_chunks[-1],
                'isSpeaking': False,
                'disconnectStream': False
            })
            
            await asyncio.sleep(2)  # Wait for processing
            
            assert len(responses_received) > 0
            # Check that we received response events
            for response in responses_received:
                assert 'transcript' in response or 'partial' in response
        finally:
            await sio.disconnect()

    async def test_asr_streaming_disconnect(self, test_api_key: str):
        """Test ASR streaming disconnect event."""
        sio = socketio.AsyncClient()
        terminate_received = False
        
        @sio.event
        async def terminate():
            nonlocal terminate_received
            terminate_received = True
        
        try:
            await sio.connect(
                f'http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(0.5)
            
            # Send disconnect signal
            await sio.emit('data', {
                'audioData': 'dummy',
                'isSpeaking': False,
                'disconnectStream': True
            })
            
            await asyncio.sleep(1)
            
            assert terminate_received
        finally:
            await sio.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.streaming
class TestTTSStreaming:
    """Test class for TTS WebSocket streaming tests."""

    async def test_tts_streaming_connection(self, test_api_key: str):
        """Test TTS streaming WebSocket connection."""
        sio = socketio.AsyncClient()
        
        try:
            await sio.connect(
                f'http://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female&apiKey={test_api_key}'
            )
            assert sio.connected
        finally:
            await sio.disconnect()

    async def test_tts_streaming_text_data(self, test_api_key: str, sample_text_chunks: List[str]):
        """Test TTS streaming with text data."""
        sio = socketio.AsyncClient()
        responses_received = []
        
        @sio.event
        async def response(data):
            responses_received.append(data)
        
        try:
            await sio.connect(
                f'http://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(0.5)  # Wait for ready
            
            # Send text chunk
            await sio.emit('data', {
                'text': sample_text_chunks[0],
                'isFinal': False
            })
            
            await asyncio.sleep(2)  # Wait for processing
            
            assert len(responses_received) > 0
            # Check that we received response events with audio
            for response in responses_received:
                assert 'audioContent' in response
        finally:
            await sio.disconnect()

    async def test_tts_streaming_multiple_chunks(self, test_api_key: str, sample_text_chunks: List[str]):
        """Test TTS streaming with multiple text chunks."""
        sio = socketio.AsyncClient()
        responses_received = []
        
        @sio.event
        async def response(data):
            responses_received.append(data)
        
        try:
            await sio.connect(
                f'http://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(0.5)
            
            # Send multiple text chunks
            for i, chunk in enumerate(sample_text_chunks):
                await sio.emit('data', {
                    'text': chunk,
                    'isFinal': i == len(sample_text_chunks) - 1
                })
                await asyncio.sleep(0.5)  # Wait between chunks
            
            await asyncio.sleep(3)  # Wait for final processing
            
            assert len(responses_received) > 0
        finally:
            await sio.disconnect()

    async def test_tts_streaming_format_conversion(self, test_api_key: str, sample_text_chunks: List[str]):
        """Test TTS streaming with audio format conversion."""
        sio = socketio.AsyncClient()
        responses_received = []
        
        @sio.event
        async def response(data):
            responses_received.append(data)
        
        try:
            await sio.connect(
                f'http://localhost:8088/socket.io/tts?serviceId=indic-tts-coqui-dravidian&voice_id=indic-tts-coqui-dravidian-female&language=ta&gender=female&audioFormat=mp3&apiKey={test_api_key}'
            )
            
            await sio.emit('start')
            await asyncio.sleep(0.5)
            
            await sio.emit('data', {
                'text': sample_text_chunks[0],
                'isFinal': True
            })
            
            await asyncio.sleep(2)
            
            assert len(responses_received) > 0
            # Check that response indicates MP3 format
            for response in responses_received:
                if 'format' in response:
                    assert response['format'] == 'mp3'
        finally:
            await sio.disconnect()
