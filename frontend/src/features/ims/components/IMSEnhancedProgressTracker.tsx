/**
 * IMS Enhanced Progress Tracker component
 * Provides real-time visual feedback for IMS crawling jobs with advanced logging and completion stats
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSSEStream } from '../hooks/useSSEStream';
import type { CompletionStats, ProgressSnapshot } from '../types/progress';

interface IMSEnhancedProgressTrackerProps {
    jobId: string;
    onComplete: (stats: CompletionStats) => void;
    onError: (error: string) => void;
    onViewResults: () => void;
}

export const IMSEnhancedProgressTracker: React.FC<IMSEnhancedProgressTrackerProps> = ({
    jobId,
    onComplete,
    onError,
    onViewResults
}) => {
    const [progress, setProgress] = useState(0);
    const [currentStep, setCurrentStep] = useState('Initializing search...');
    const [status, setStatus] = useState<'pending' | 'running' | 'completed' | 'failed'>('pending');
    const [stats, setStats] = useState({
        found: 0,
        crawled: 0,
        related: 0,
        startTime: Date.now()
    });
    const [logs, setLogs] = useState<{ id: string; message: string; type: 'info' | 'success' | 'error' | 'warning'; timestamp: string }[]>([]);
    const scrollRef = useRef<HTMLDivElement>(null);

    const addLog = useCallback((message: string, type: 'info' | 'success' | 'error' | 'warning' = 'info') => {
        const newLog = {
            id: Math.random().toString(36).substr(2, 9),
            message,
            type,
            timestamp: new Date().toLocaleTimeString()
        };
        setLogs(prev => [...prev.slice(-49), newLog]);
    }, []);

    // Monitor SSE stream
    const { data, isConnected, error: sseError } = useSSEStream(`/api/v1/ims-jobs/${jobId}/stream`, {
        autoConnect: true
    });

    // Automatically scroll logs
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs]);

    // Handle SSE data
    useEffect(() => {
        if (!data) return;

        const { event, message, ...payload } = data;

        switch (event) {
            case 'job_started':
                setStatus('running');
                setCurrentStep('Search started...');
                addLog('Crawl job started', 'info');
                break;

            case 'searching':
                setCurrentStep(`Searching: ${message || 'Looking for issues...'}`);
                addLog(`Search query executing...`, 'info');
                break;

            case 'search_completed':
                const total = payload.total_issues || 0;
                setStats(prev => ({ ...prev, found: total }));
                setCurrentStep(`Found ${total} issues. Starting crawl...`);
                addLog(`Found ${total} issues matching criteria`, 'success');
                break;

            case 'crawling_issue':
                const current = payload.issue_number || 0;
                const totalCount = payload.total_issues || stats.found;
                const percentage = totalCount > 0 ? Math.round((current / totalCount) * 100) : 0;

                setProgress(percentage);
                setStats(prev => ({ ...prev, crawled: current }));
                setCurrentStep(`Processing issue ${current} of ${totalCount}...`);
                if (payload.issue_id) {
                    addLog(`Crawling ${payload.issue_id}`, 'info');
                }
                break;

            case 'related_issues_found':
                const related = payload.related_count || 0;
                setStats(prev => ({ ...prev, related: prev.related + related }));
                addLog(`Found ${related} related issues`, 'info');
                break;

            case 'job_completed':
                setStatus('completed');
                setProgress(100);
                setCurrentStep('Crawl completed successfully');
                addLog('Job finished successfully', 'success');

                // Create completion stats
                const duration = (Date.now() - stats.startTime) / 1000;
                const finalStats: CompletionStats = {
                    totalIssues: stats.found,
                    successfulIssues: payload.crawled_issues || stats.crawled,
                    duration,
                    outcome: 'success',
                    relatedIssues: stats.related,
                    progressSnapshot: {
                        status: 'completed',
                        progress: 100,
                        currentStep: 'Completed',
                        timestamp: new Date().toISOString(),
                        issuesFound: stats.found,
                        issuesCrawled: payload.crawled_issues || stats.crawled,
                        relatedCount: stats.related
                    }
                };

                onComplete(finalStats);
                break;

            case 'job_failed':
                setStatus('failed');
                setCurrentStep('Job failed');
                addLog(`Error: ${payload.error || 'Unknown error'}`, 'error');
                onError(payload.error || 'Job failed');
                break;

            case 'error':
                addLog(`Stream error: ${message}`, 'error');
                // Don't necessarily fail the whole job on a single stream error
                break;
        }
    }, [data, onComplete, onError, stats.found, stats.crawled, stats.related, stats.startTime, addLog]);

    // Handle SSE errors
    useEffect(() => {
        if (sseError) {
            addLog(`Connection error: ${sseError}`, 'warning');
        }
    }, [sseError, addLog]);

    return (
        <div style={{
            padding: '24px',
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '16px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.12)',
            marginTop: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '24px'
        }}>
            {/* Header & Status */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                        width: '10px',
                        height: '10px',
                        borderRadius: '50%',
                        background: isConnected ? '#10b981' : '#ef4444',
                        boxShadow: `0 0 8px ${isConnected ? '#10b981' : '#ef4444'}`
                    }} />
                    <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>Active Search Progress</h3>
                </div>
                <div style={{ fontSize: '14px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                    ID: {jobId.split('-')[0]}...
                </div>
            </div>

            {/* Progress Section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', fontWeight: 600 }}>
                    <span>{currentStep}</span>
                    <span style={{ color: 'var(--accent)' }}>{progress}%</span>
                </div>
                <div style={{
                    width: '100%',
                    height: '12px',
                    background: 'var(--bg-secondary)',
                    borderRadius: '6px',
                    overflow: 'hidden',
                    border: '1px solid var(--border)'
                }}>
                    <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ type: 'spring', stiffness: 50, damping: 20 }}
                        style={{
                            height: '100%',
                            background: 'linear-gradient(90deg, var(--accent) 0%, #60a5fa 100%)',
                            boxShadow: '0 0 10px rgba(59, 130, 246, 0.5)'
                        }}
                    />
                </div>
            </div>

            {/* Stats Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>{stats.found}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Found</div>
                </div>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: '#10b981' }}>{stats.crawled}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Crawled</div>
                </div>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: '#f59e0b' }}>{stats.related}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Related</div>
                </div>
            </div>

            {/* Logs Section */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)' }}>Activity Log</h4>
                <div
                    ref={scrollRef}
                    style={{
                        height: '160px',
                        background: 'var(--bg)',
                        border: '1px solid var(--border)',
                        borderRadius: '12px',
                        padding: '12px',
                        overflowY: 'auto',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '6px',
                        fontFamily: 'monospace',
                        fontSize: '12px'
                    }}
                >
                    <AnimatePresence initial={false}>
                        {logs.map(log => (
                            <motion.div
                                key={log.id}
                                initial={{ opacity: 0, y: 5 }}
                                animate={{ opacity: 1, y: 0 }}
                                style={{
                                    color: log.type === 'error' ? '#ef4444' :
                                        log.type === 'success' ? '#10b981' :
                                            log.type === 'warning' ? '#f59e0b' : 'var(--text-secondary)',
                                    display: 'flex',
                                    gap: '8px'
                                }}
                            >
                                <span style={{ opacity: 0.5 }}>[{log.timestamp}]</span>
                                <span>{log.message}</span>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                    {logs.length === 0 && (
                        <div style={{ color: 'var(--text-secondary)', opacity: 0.5, fontStyle: 'italic' }}>
                            Waiting for activity...
                        </div>
                    )}
                </div>
            </div>

            {/* Actions */}
            {status === 'completed' && (
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    style={{
                        display: 'flex',
                        justifyContent: 'center',
                        paddingTop: '8px'
                    }}
                >
                    <button
                        onClick={onViewResults}
                        style={{
                            padding: '12px 32px',
                            background: 'var(--accent)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            fontSize: '16px',
                            fontWeight: 700,
                            cursor: 'pointer',
                            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px'
                        }}
                    >
                        📊 View Full Analysis
                    </button>
                </motion.div>
            )}
        </div>
    );
};

export default IMSEnhancedProgressTracker;
