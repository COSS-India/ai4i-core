// Custom React hook for WebSocket streaming using Socket.IO client

import { useState, useEffect, useRef, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { useToast } from '@chakra-ui/react';
import { StreamingConfig, SocketStatus } from '../types/common';

interface UseWebSocketOptions {
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectDelay?: number;
}

interface UseWebSocketReturn {
  socket: Socket | null;
  isConnected: boolean;
  status: SocketStatus;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  sendData: (data: any) => void;
  sendAudioData: (audioData: ArrayBuffer) => void;
}

export const useWebSocket = (
  url: string,
  config: StreamingConfig,
  onMessage: (data: any) => void,
  onError?: (error: any) => void,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn => {
  const {
    autoConnect = true,
    reconnectAttempts = 5,
    reconnectDelay = 1000,
  } = options;

  // State
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [status, setStatus] = useState<SocketStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);

  // Refs
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Toast hook
  const toast = useToast();

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (socket && socket.connected) {
      return;
    }

    try {
      setStatus('connecting');
      setError(null);

      const newSocket = io(url, {
        transports: ['websocket'],
        query: config,
        timeout: 10000,
        reconnection: false, // Handle reconnection manually
      });

      // Connection event handlers
      newSocket.on('connect', () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setStatus('connected');
        setError(null);
        reconnectAttemptsRef.current = 0;
        
        // Emit start event after connection
        newSocket.emit('start');
      });

      newSocket.on('disconnect', (reason) => {
        console.log('WebSocket disconnected:', reason);
        setIsConnected(false);
        setStatus('disconnected');
        
        // Attempt reconnection if not manual disconnect
        if (reason !== 'io client disconnect' && reconnectAttemptsRef.current < reconnectAttempts) {
          reconnectAttemptsRef.current++;
          setStatus('connecting');
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectDelay * reconnectAttemptsRef.current);
        }
      });

      newSocket.on('connect_error', (err) => {
        console.error('WebSocket connection error:', err);
        setError(err.message);
        setStatus('error');
        setIsConnected(false);
        
        if (onError) {
          onError(err);
        }
      });

      // Message handlers
      newSocket.on('response', (data) => {
        try {
          onMessage(data);
        } catch (err) {
          console.error('Error handling message:', err);
        }
      });

      newSocket.on('error', (err) => {
        console.error('WebSocket error:', err);
        setError(err.error || err.message || 'Unknown error');
        setStatus('error');
        
        if (onError) {
          onError(err);
        }
      });

      setSocket(newSocket);
    } catch (err) {
      console.error('Error creating WebSocket connection:', err);
      setError('Failed to create WebSocket connection');
      setStatus('error');
    }
  }, [url, config, onMessage, onError, reconnectAttempts, reconnectDelay, socket]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (socket) {
      // Clear reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Emit disconnect event
      socket.emit('data', { disconnectStream: true });
      
      // Disconnect socket
      socket.disconnect();
      setSocket(null);
    }
    
    setIsConnected(false);
    setStatus('disconnected');
    setError(null);
  }, [socket]);

  // Send data through WebSocket
  const sendData = useCallback((data: any) => {
    if (socket && isConnected) {
      try {
        socket.emit('data', data);
      } catch (err) {
        console.error('Error sending data:', err);
        setError('Failed to send data');
      }
    } else {
      console.warn('WebSocket not connected, cannot send data');
      setError('WebSocket not connected');
    }
  }, [socket, isConnected]);

  // Send audio data through WebSocket
  const sendAudioData = useCallback((audioData: ArrayBuffer) => {
    if (socket && isConnected) {
      try {
        // Convert ArrayBuffer to base64
        const uint8Array = new Uint8Array(audioData);
        const base64 = btoa(Array.from(uint8Array, byte => String.fromCharCode(byte)).join(''));
        
        socket.emit('data', {
          audio: base64,
          timestamp: Date.now(),
        });
      } catch (err) {
        console.error('Error sending audio data:', err);
        setError('Failed to send audio data');
      }
    } else {
      console.warn('WebSocket not connected, cannot send audio data');
      setError('WebSocket not connected');
    }
  }, [socket, isConnected]);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    socket,
    isConnected,
    status,
    error,
    connect,
    disconnect,
    sendData,
    sendAudioData,
  };
};
