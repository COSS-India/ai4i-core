/**
 * Unit tests for useASR hook.
 */
import { renderHook, act } from '@testing-library/react-hooks';
import { useASR } from '@/hooks/useASR';

// Mock the asrService
jest.mock('@/services/asrService', () => ({
  performASRInference: jest.fn(),
}));

// Mock Recorder.js
const mockRecorder = {
  record: jest.fn(),
  stop: jest.fn(),
  exportWAV: jest.fn((callback) => {
    const blob = new Blob(['dummy audio data'], { type: 'audio/wav' });
    callback(blob);
  }),
};

global.Recorder = jest.fn(() => mockRecorder);

describe('useASR Hook', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Mock successful getUserMedia
    (navigator.mediaDevices.getUserMedia as jest.Mock).mockResolvedValue({
      getTracks: () => [{
        stop: jest.fn(),
        kind: 'audio',
      }],
    });
  });

  test('initializes with default state', () => {
    const { result } = renderHook(() => useASR());

    expect(result.current.recording).toBe(false);
    expect(result.current.fetching).toBe(false);
    expect(result.current.fetched).toBe(false);
    expect(result.current.audioText).toBe('');
    expect(result.current.permissionDenied).toBe(false);
  });

  test('requests microphone permission on mount', async () => {
    renderHook(() => useASR());

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
  });

  test('handles permission denied', async () => {
    (navigator.mediaDevices.getUserMedia as jest.Mock).mockRejectedValue(
      new Error('Permission denied')
    );

    const { result } = renderHook(() => useASR());

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100));
    });

    expect(result.current.permissionDenied).toBe(true);
  });

  test('startRecording creates recorder and starts recording', async () => {
    const { result } = renderHook(() => useASR());

    await act(async () => {
      result.current.startRecording();
    });

    expect(result.current.recording).toBe(true);
    expect(global.Recorder).toHaveBeenCalled();
    expect(mockRecorder.record).toHaveBeenCalled();
  });

  test('stopRecording stops recorder and exports WAV', async () => {
    const { result } = renderHook(() => useASR());

    await act(async () => {
      result.current.startRecording();
    });

    await act(async () => {
      result.current.stopRecording();
    });

    expect(result.current.recording).toBe(false);
    expect(mockRecorder.stop).toHaveBeenCalled();
    expect(mockRecorder.exportWAV).toHaveBeenCalled();
  });

  test('performInference calls API and updates audioText', async () => {
    const mockResponse = {
      output: [{ source: 'Hello, this is a test transcription.' }]
    };

    const { performASRInference } = require('@/services/asrService');
    performASRInference.mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useASR());

    await act(async () => {
      await result.current.performInference('base64data');
    });

    expect(performASRInference).toHaveBeenCalledWith({
      audio: [{ audioContent: 'base64data' }],
      config: expect.any(Object)
    });
    expect(result.current.audioText).toBe('Hello, this is a test transcription.');
    expect(result.current.fetched).toBe(true);
  });

  test('handleFileUpload reads file and calls performInference', async () => {
    const mockFile = new File(['dummy audio data'], 'test.wav', { type: 'audio/wav' });
    const mockFileReader = {
      readAsDataURL: jest.fn(),
      result: 'data:audio/wav;base64,dummy_base64_data',
      onload: null,
    };

    // Mock FileReader
    global.FileReader = jest.fn(() => mockFileReader) as any;

    const { result } = renderHook(() => useASR());

    await act(async () => {
      result.current.handleFileUpload(mockFile);
    });

    expect(mockFileReader.readAsDataURL).toHaveBeenCalledWith(mockFile);
  });

  test('handles API errors gracefully', async () => {
    const { performASRInference } = require('@/services/asrService');
    performASRInference.mockRejectedValue(new Error('API Error'));

    const { result } = renderHook(() => useASR());

    await act(async () => {
      try {
        await result.current.performInference('base64data');
      } catch (error) {
        // Error should be handled
      }
    });

    expect(result.current.fetched).toBe(false);
    expect(result.current.audioText).toBe('');
  });

  test('resets state when starting new recording', async () => {
    const { result } = renderHook(() => useASR());

    // Set some state
    act(() => {
      result.current.setAudioText('Previous text');
    });

    await act(async () => {
      result.current.startRecording();
    });

    expect(result.current.audioText).toBe('');
    expect(result.current.fetched).toBe(false);
  });
});
