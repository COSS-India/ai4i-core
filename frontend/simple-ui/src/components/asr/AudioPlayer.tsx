// Audio player component with waveform visualization

import React, { useRef, useEffect, useState } from 'react';
import {
  VStack,
  Box,
  Text,
  Button,
  HStack,
  Slider,
  SliderTrack,
  SliderFilledTrack,
  SliderThumb,
  useToast,
} from '@chakra-ui/react';
import { FaPlay, FaPause, FaDownload } from 'react-icons/fa';
import { AudioPlayerProps } from '../../types/asr';
import { formatDuration } from '../../utils/helpers';

const AudioPlayer: React.FC<AudioPlayerProps> = ({
  audioSrc,
  showVisualization = true,
  onPlay,
  onPause,
  onEnded,
}) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const toast = useToast();

  // Audio event handlers
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const handlePlay = () => {
      setIsPlaying(true);
      onPlay?.();
    };

    const handlePause = () => {
      setIsPlaying(false);
      onPause?.();
    };

    const handleEnded = () => {
      setIsPlaying(false);
      setCurrentTime(0);
      onEnded?.();
    };

    const handleTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
    };

    const handleLoadedMetadata = () => {
      setDuration(audio.duration);
    };

    const handleVolumeChange = () => {
      setVolume(audio.volume);
    };

    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('volumechange', handleVolumeChange);

    return () => {
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('volumechange', handleVolumeChange);
    };
  }, [onPlay, onPause, onEnded]);

  // Waveform visualization
  useEffect(() => {
    if (!showVisualization || !canvasRef.current || !audioRef.current) return;

    const canvas = canvasRef.current;
    const audio = audioRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    // Create audio context for visualization
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaElementSource(audio);
    
    source.connect(analyser);
    analyser.connect(audioContext.destination);
    
    analyser.fftSize = 256;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      if (!isPlaying) return;
      
      requestAnimationFrame(draw);
      
      analyser.getByteFrequencyData(dataArray);
      
      ctx.fillStyle = '#f7fafc';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      const barWidth = (canvas.width / bufferLength) * 2.5;
      let barHeight;
      let x = 0;
      
      for (let i = 0; i < bufferLength; i++) {
        barHeight = (dataArray[i] / 255) * canvas.height;
        
        const gradient = ctx.createLinearGradient(0, canvas.height - barHeight, 0, canvas.height);
        gradient.addColorStop(0, '#ff8c00');
        gradient.addColorStop(1, '#ff6b00');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
        
        x += barWidth + 1;
      }
    };

    if (isPlaying) {
      draw();
    }

    return () => {
      audioContext.close();
    };
  }, [isPlaying, showVisualization]);

  const handlePlayPause = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch((error) => {
        console.error('Error playing audio:', error);
        toast({
          title: 'Playback Error',
          description: 'Failed to play audio. Please try again.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      });
    }
  };

  const handleSeek = (value: number) => {
    const audio = audioRef.current;
    if (!audio) return;

    audio.currentTime = value;
    setCurrentTime(value);
  };

  const handleVolumeChange = (value: number) => {
    const audio = audioRef.current;
    if (!audio) return;

    audio.volume = value;
    setVolume(value);
  };

  const handleDownload = () => {
    if (!audioSrc) return;

    try {
      const link = document.createElement('a');
      link.href = audioSrc;
      link.download = `audio_${Date.now()}.wav`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Error downloading audio:', error);
      toast({
        title: 'Download Error',
        description: 'Failed to download audio. Please try again.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };

  if (!audioSrc) {
    return (
      <Box p={8} textAlign="center" color="gray.500">
        <Text>No audio to play</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} w="full" maxW="600px">
      {/* Waveform Visualization */}
      {showVisualization && (
        <Box w="full" h="100px" border="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
          <canvas
            ref={canvasRef}
            style={{ width: '100%', height: '100%' }}
          />
        </Box>
      )}

      {/* Audio Element */}
      <audio
        ref={audioRef}
        src={audioSrc}
        preload="metadata"
        style={{ display: 'none' }}
      />

      {/* Playback Controls */}
      <HStack spacing={4} w="full">
        <Button
          leftIcon={isPlaying ? <FaPause /> : <FaPlay />}
          onClick={handlePlayPause}
          colorScheme="orange"
          size="sm"
        >
          {isPlaying ? 'Pause' : 'Play'}
        </Button>

        <Button
          leftIcon={<FaDownload />}
          onClick={handleDownload}
          variant="outline"
          size="sm"
        >
          Download
        </Button>
      </HStack>

      {/* Progress Bar */}
      <VStack spacing={2} w="full">
        <Slider
          value={currentTime}
          min={0}
          max={duration || 0}
          onChange={handleSeek}
          isDisabled={!duration}
          colorScheme="orange"
        >
          <SliderTrack>
            <SliderFilledTrack />
          </SliderTrack>
          <SliderThumb />
        </Slider>

        <HStack justify="space-between" w="full" fontSize="sm" color="gray.600">
          <Text>{formatDuration(currentTime)}</Text>
          <Text>{formatDuration(duration)}</Text>
        </HStack>
      </VStack>

      {/* Volume Control */}
      <HStack spacing={4} w="full">
        <Text fontSize="sm" minW="60px">Volume:</Text>
        <Slider
          value={volume}
          min={0}
          max={1}
          step={0.1}
          onChange={handleVolumeChange}
          colorScheme="orange"
          flex={1}
        >
          <SliderTrack>
            <SliderFilledTrack />
          </SliderTrack>
          <SliderThumb />
        </Slider>
        <Text fontSize="sm" minW="30px">{Math.round(volume * 100)}%</Text>
      </HStack>
    </VStack>
  );
};

export default AudioPlayer;
