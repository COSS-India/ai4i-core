/**
 * Unit tests for AudioRecorder component.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AudioRecorder from '@/components/AudioRecorder';

// Mock the useASR hook
const mockUseASR = {
  recording: false,
  fetching: false,
  permissionDenied: false,
  startRecording: jest.fn(),
  stopRecording: jest.fn(),
  handleFileUpload: jest.fn(),
};

jest.mock('@/hooks/useASR', () => ({
  useASR: () => mockUseASR,
}));

// Mock Chakra UI components
const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ChakraProvider>
        {component}
      </ChakraProvider>
    </QueryClientProvider>
  );
};

describe('AudioRecorder Component', () => {
  const mockProps = {
    onRecordingChange: jest.fn(),
    onAudioReady: jest.fn(),
    isRecording: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders record button', () => {
    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const recordButton = screen.getByTestId('record-button');
    expect(recordButton).toBeInTheDocument();
    expect(recordButton).toHaveTextContent('Record');
  });

  test('renders file upload button', () => {
    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const fileButton = screen.getByTestId('file-upload-button');
    expect(fileButton).toBeInTheDocument();
    expect(fileButton).toHaveTextContent('Choose file');
  });

  test('record button click starts recording', async () => {
    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const recordButton = screen.getByTestId('record-button');
    fireEvent.click(recordButton);
    
    expect(mockUseASR.startRecording).toHaveBeenCalled();
    expect(mockProps.onRecordingChange).toHaveBeenCalledWith(true);
  });

  test('stop button click stops recording', async () => {
    const propsWithRecording = { ...mockProps, isRecording: true };
    renderWithProviders(<AudioRecorder {...propsWithRecording} />);
    
    const stopButton = screen.getByTestId('stop-button');
    fireEvent.click(stopButton);
    
    expect(mockUseASR.stopRecording).toHaveBeenCalled();
    expect(mockProps.onRecordingChange).toHaveBeenCalledWith(false);
  });

  test('file upload triggers callback', async () => {
    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const fileInput = screen.getByTestId('file-input');
    const mockFile = new File(['dummy audio data'], 'test.wav', { type: 'audio/wav' });
    
    fireEvent.change(fileInput, { target: { files: [mockFile] } });
    
    expect(mockUseASR.handleFileUpload).toHaveBeenCalledWith(mockFile);
  });

  test('shows recording timer when recording', () => {
    const propsWithRecording = { ...mockProps, isRecording: true };
    renderWithProviders(<AudioRecorder {...propsWithRecording} />);
    
    const timer = screen.getByTestId('recording-timer');
    expect(timer).toBeInTheDocument();
    expect(timer).toHaveTextContent('Recording Time:');
  });

  test('shows permission denied alert', () => {
    const mockUseASRWithPermissionDenied = {
      ...mockUseASR,
      permissionDenied: true,
    };

    jest.doMock('@/hooks/useASR', () => ({
      useASR: () => mockUseASRWithPermissionDenied,
    }));

    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const alert = screen.getByTestId('permission-denied-alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent('microphone permission');
  });

  test('shows loading state when fetching', () => {
    const mockUseASRWithFetching = {
      ...mockUseASR,
      fetching: true,
    };

    jest.doMock('@/hooks/useASR', () => ({
      useASR: () => mockUseASRWithFetching,
    }));

    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const loadingSpinner = screen.getByTestId('loading-spinner');
    expect(loadingSpinner).toBeInTheDocument();
  });

  test('disables buttons when fetching', () => {
    const mockUseASRWithFetching = {
      ...mockUseASR,
      fetching: true,
    };

    jest.doMock('@/hooks/useASR', () => ({
      useASR: () => mockUseASRWithFetching,
    }));

    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    const recordButton = screen.getByTestId('record-button');
    const fileButton = screen.getByTestId('file-upload-button');
    
    expect(recordButton).toBeDisabled();
    expect(fileButton).toBeDisabled();
  });

  test('handles recording state changes', async () => {
    const { rerender } = renderWithProviders(<AudioRecorder {...mockProps} />);
    
    // Initially not recording
    expect(screen.getByTestId('record-button')).toBeInTheDocument();
    expect(screen.queryByTestId('stop-button')).not.toBeInTheDocument();
    
    // Change to recording state
    const propsWithRecording = { ...mockProps, isRecording: true };
    rerender(<AudioRecorder {...propsWithRecording} />);
    
    expect(screen.queryByTestId('record-button')).not.toBeInTheDocument();
    expect(screen.getByTestId('stop-button')).toBeInTheDocument();
  });

  test('calls onAudioReady when audio is processed', async () => {
    // Mock the useASR hook to simulate audio processing
    const mockUseASRWithAudio = {
      ...mockUseASR,
      audioText: 'Processed audio text',
    };

    jest.doMock('@/hooks/useASR', () => ({
      useASR: () => mockUseASRWithAudio,
    }));

    renderWithProviders(<AudioRecorder {...mockProps} />);
    
    // Simulate audio processing completion
    await waitFor(() => {
      expect(mockProps.onAudioReady).toHaveBeenCalled();
    });
  });
});
