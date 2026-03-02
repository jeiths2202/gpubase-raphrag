/**
 * Premium Support Panel
 *
 * LiveKit 기반 원격 전문가 화면 공유 오버레이 패널.
 * Open Agent 페이지 채팅 영역 위에 표시됨.
 */
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  Headphones,
  X,
  Loader2,
  AlertCircle,
  Monitor,
  MonitorOff,
  Mic,
  MicOff,
  PhoneOff,
  User,
} from 'lucide-react';
import { premiumSupportApi } from '../../api/premium-support.api';
import './PremiumSupportPanel.css';

type SessionState = 'idle' | 'connecting' | 'waiting' | 'active' | 'error';

interface PremiumSupportPanelProps {
  isOpen: boolean;
  onClose: () => void;
  chatContext?: string;
}

export const PremiumSupportPanel: React.FC<PremiumSupportPanelProps> = ({
  isOpen,
  onClose,
  chatContext,
}) => {
  const { t } = useTranslation();
  const [sessionState, setSessionState] = useState<SessionState>('idle');
  const [roomName, setRoomName] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [isMicOn, setIsMicOn] = useState(true);
  const [expertName, setExpertName] = useState<string>('');

  // LiveKit Room reference (dynamic import)
  const roomRef = useRef<any>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);

  // 세션 시작
  const startSession = useCallback(async () => {
    setSessionState('connecting');
    setErrorMsg('');

    try {
      const response = await premiumSupportApi.createSession({
        chat_context: chatContext,
      });
      const data = response.data;

      setRoomName(data.room_name);
      setSessionState('waiting');

      // LiveKit 연결 시도 (dynamic import, hidden from Vite static analysis)
      try {
        const livekitModule = 'livekit-client';
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const { Room, RoomEvent } = await import(/* @vite-ignore */ livekitModule);

        const room = new Room();
        roomRef.current = room;

        // 참가자 연결 이벤트
        room.on(RoomEvent.ParticipantConnected, (participant: any) => {
          setExpertName(participant.name || participant.identity);
          setSessionState('active');
        });

        // 참가자 연결 해제
        room.on(RoomEvent.ParticipantDisconnected, () => {
          setExpertName('');
          setSessionState('waiting');
        });

        // Room 연결 해제
        room.on(RoomEvent.Disconnected, () => {
          setSessionState('idle');
        });

        await room.connect(data.server_url, data.token);
      } catch (lkError) {
        console.error('LiveKit connection failed:', lkError);
        // LiveKit SDK 미설치 시에도 UI는 동작 (세션 생성까지는 성공)
        setSessionState('waiting');
      }
    } catch (error: any) {
      console.error('Session creation failed:', error);
      setErrorMsg(
        error?.response?.data?.detail || t('common.openAgent.sessionError')
      );
      setSessionState('error');
    }
  }, [chatContext, t]);

  // 세션 종료
  const endSession = useCallback(async () => {
    // LiveKit Room 해제
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }

    // 화면 공유 스트림 해제
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      screenStreamRef.current = null;
    }

    // 서버에 세션 종료 알림
    if (roomName) {
      try {
        await premiumSupportApi.endSession({ room_name: roomName });
      } catch (e) {
        console.warn('End session API call failed:', e);
      }
    }

    setSessionState('idle');
    setRoomName('');
    setIsScreenSharing(false);
    setIsMicOn(true);
    setExpertName('');
    onClose();
  }, [roomName, onClose]);

  // 화면 공유 토글
  const toggleScreenShare = useCallback(async () => {
    if (isScreenSharing) {
      // 화면 공유 중지
      if (screenStreamRef.current) {
        screenStreamRef.current.getTracks().forEach((track: MediaStreamTrack) => track.stop());
        screenStreamRef.current = null;
      }
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = null;
      }
      // LiveKit에서도 중지
      if (roomRef.current?.localParticipant) {
        await roomRef.current.localParticipant.setScreenShareEnabled(false);
      }
      setIsScreenSharing(false);
    } else {
      // 화면 공유 시작
      try {
        if (roomRef.current?.localParticipant) {
          // LiveKit 방식
          await roomRef.current.localParticipant.setScreenShareEnabled(true);
          setIsScreenSharing(true);
        } else {
          // Fallback: 브라우저 네이티브 getDisplayMedia
          const stream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: false,
          });
          screenStreamRef.current = stream;
          if (localVideoRef.current) {
            localVideoRef.current.srcObject = stream;
          }
          // 사용자가 브라우저에서 공유 중지하면 이벤트 처리
          stream.getVideoTracks()[0].onended = () => {
            setIsScreenSharing(false);
            screenStreamRef.current = null;
            if (localVideoRef.current) {
              localVideoRef.current.srcObject = null;
            }
          };
          setIsScreenSharing(true);
        }
      } catch (err) {
        console.error('Screen share failed:', err);
      }
    }
  }, [isScreenSharing]);

  // 마이크 토글
  const toggleMic = useCallback(async () => {
    if (roomRef.current?.localParticipant) {
      await roomRef.current.localParticipant.setMicrophoneEnabled(!isMicOn);
    }
    setIsMicOn(!isMicOn);
  }, [isMicOn]);

  // 패널 닫을 때 정리
  useEffect(() => {
    if (!isOpen && sessionState !== 'idle') {
      // 패널 닫힘 but 세션 진행 중이면 종료하지 않음 (사용자가 X로 닫은 경우)
    }
  }, [isOpen, sessionState]);

  if (!isOpen) return null;

  return (
    <div className="premium-support-overlay">
      <div className="premium-support-panel">
        {/* Header */}
        <div className="premium-support-header">
          <div className="premium-support-header-left">
            <Headphones size={20} />
            <h3>{t('common.openAgent.premiumSupport')}</h3>
          </div>
          <button
            className="premium-support-close"
            onClick={endSession}
            title="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="premium-support-content">
          {/* Idle: 시작 안내 */}
          {sessionState === 'idle' && (
            <div className="premium-support-start">
              <Headphones size={48} className="premium-support-hero-icon" />
              <p className="premium-support-desc">
                {t('common.openAgent.premiumSupportDesc')}
              </p>
              <button
                className="premium-support-btn-start"
                onClick={startSession}
              >
                {t('common.openAgent.startSession')}
              </button>
            </div>
          )}

          {/* Connecting */}
          {sessionState === 'connecting' && (
            <div className="premium-support-center">
              <Loader2 size={36} className="premium-support-spinner" />
              <p>{t('common.openAgent.connecting')}</p>
            </div>
          )}

          {/* Waiting for expert */}
          {sessionState === 'waiting' && (
            <div className="premium-support-center">
              <div className="premium-support-waiting-ring">
                <User size={32} />
              </div>
              <p className="premium-support-waiting-text">
                {t('common.openAgent.waitingForExpert')}
              </p>
              {/* 화면 공유 프리뷰 */}
              <div className="premium-support-preview">
                <video
                  ref={localVideoRef}
                  autoPlay
                  muted
                  playsInline
                  className="premium-support-video"
                />
                {!isScreenSharing && (
                  <div className="premium-support-video-placeholder">
                    <Monitor size={32} />
                    <span>{t('common.openAgent.shareScreen')}</span>
                  </div>
                )}
              </div>
              {/* Controls */}
              <div className="premium-support-controls">
                <button
                  className={`premium-support-ctrl-btn ${isScreenSharing ? 'active' : ''}`}
                  onClick={toggleScreenShare}
                  title={isScreenSharing ? t('common.openAgent.stopSharing') : t('common.openAgent.shareScreen')}
                >
                  {isScreenSharing ? <MonitorOff size={18} /> : <Monitor size={18} />}
                  <span>{isScreenSharing ? t('common.openAgent.stopSharing') : t('common.openAgent.shareScreen')}</span>
                </button>
                <button
                  className={`premium-support-ctrl-btn ${!isMicOn ? 'muted' : ''}`}
                  onClick={toggleMic}
                  title={isMicOn ? t('common.openAgent.micOn') : t('common.openAgent.micOff')}
                >
                  {isMicOn ? <Mic size={18} /> : <MicOff size={18} />}
                </button>
                <button
                  className="premium-support-ctrl-btn end"
                  onClick={endSession}
                  title={t('common.openAgent.endSession')}
                >
                  <PhoneOff size={18} />
                  <span>{t('common.openAgent.endSession')}</span>
                </button>
              </div>
            </div>
          )}

          {/* Active session */}
          {sessionState === 'active' && (
            <div className="premium-support-active">
              <div className="premium-support-expert-badge">
                <User size={16} />
                <span>{t('common.openAgent.expertConnected')}: {expertName}</span>
              </div>
              {/* 화면 공유 프리뷰 */}
              <div className="premium-support-preview">
                <video
                  ref={localVideoRef}
                  autoPlay
                  muted
                  playsInline
                  className="premium-support-video"
                />
                {!isScreenSharing && (
                  <div className="premium-support-video-placeholder">
                    <Monitor size={32} />
                    <span>{t('common.openAgent.shareScreen')}</span>
                  </div>
                )}
              </div>
              {/* Controls */}
              <div className="premium-support-controls">
                <button
                  className={`premium-support-ctrl-btn ${isScreenSharing ? 'active' : ''}`}
                  onClick={toggleScreenShare}
                >
                  {isScreenSharing ? <MonitorOff size={18} /> : <Monitor size={18} />}
                  <span>{isScreenSharing ? t('common.openAgent.stopSharing') : t('common.openAgent.shareScreen')}</span>
                </button>
                <button
                  className={`premium-support-ctrl-btn ${!isMicOn ? 'muted' : ''}`}
                  onClick={toggleMic}
                >
                  {isMicOn ? <Mic size={18} /> : <MicOff size={18} />}
                </button>
                <button
                  className="premium-support-ctrl-btn end"
                  onClick={endSession}
                >
                  <PhoneOff size={18} />
                  <span>{t('common.openAgent.endSession')}</span>
                </button>
              </div>
            </div>
          )}

          {/* Error */}
          {sessionState === 'error' && (
            <div className="premium-support-center">
              <AlertCircle size={36} className="premium-support-error-icon" />
              <p className="premium-support-error-text">
                {errorMsg || t('common.openAgent.sessionError')}
              </p>
              <button
                className="premium-support-btn-retry"
                onClick={() => setSessionState('idle')}
              >
                {t('common.retry') || 'Retry'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PremiumSupportPanel;
