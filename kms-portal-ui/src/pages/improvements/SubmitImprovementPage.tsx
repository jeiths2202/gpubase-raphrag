/**
 * Submit Improvement Page
 *
 * Form for submitting new enhancement requests
 */

import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Upload,
  X,
  FileText,
  Image,
  File,
  Bot,
  Send,
  Loader2,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  createEnhancement,
  uploadAttachment,
  EnhancementType,
  EnhancementPriority,
} from '../../api/improvements.api';
import './SubmitImprovementPage.css';

interface UploadedFile {
  file: File;
  preview?: string;
}

export const SubmitImprovementPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [type, setType] = useState<EnhancementType | ''>('');
  const [priority, setPriority] = useState<EnhancementPriority | ''>('');
  const [files, setFiles] = useState<UploadedFile[]>([]);

  // UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // File type icons
  const getFileIcon = (file: File) => {
    if (file.type.startsWith('image/')) return <Image size={20} />;
    if (file.type.includes('pdf') || file.type.includes('document')) return <FileText size={20} />;
    return <File size={20} />;
  };

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Handle file selection
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles) return;

    const newFiles: UploadedFile[] = [];
    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];
      const uploadedFile: UploadedFile = { file };

      // Generate preview for images
      if (file.type.startsWith('image/')) {
        uploadedFile.preview = URL.createObjectURL(file);
      }

      newFiles.push(uploadedFile);
    }

    setFiles([...files, ...newFiles]);

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Handle drag and drop
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFiles = e.dataTransfer.files;
    if (!droppedFiles) return;

    const newFiles: UploadedFile[] = [];
    for (let i = 0; i < droppedFiles.length; i++) {
      const file = droppedFiles[i];
      const uploadedFile: UploadedFile = { file };

      if (file.type.startsWith('image/')) {
        uploadedFile.preview = URL.createObjectURL(file);
      }

      newFiles.push(uploadedFile);
    }

    setFiles([...files, ...newFiles]);
  };

  // Remove file
  const removeFile = (index: number) => {
    const newFiles = [...files];
    const removed = newFiles.splice(index, 1);
    if (removed[0]?.preview) {
      URL.revokeObjectURL(removed[0].preview);
    }
    setFiles(newFiles);
  };

  // Submit form
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      // Create enhancement
      const result = await createEnhancement({
        title,
        description,
        type: type || undefined,
        priority: priority || undefined,
      });

      // Upload attachments
      for (const uploadedFile of files) {
        try {
          await uploadAttachment(result.id, uploadedFile.file);
        } catch (uploadError) {
          console.error('Failed to upload attachment:', uploadError);
        }
      }

      // Navigate to the created enhancement
      navigate(`/improvements/${result.id}`);
    } catch (err) {
      setError(t('improvements.errors.createFailed'));
      console.error('Failed to create enhancement:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="submit-improvement-page">
      {/* Header */}
      <div className="page-header">
        <button className="btn-back" onClick={() => navigate('/improvements')}>
          <ArrowLeft size={20} />
          {t('common.back')}
        </button>
        <h1>{t('improvements.submit')}</h1>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="improvement-form">
        {/* Title */}
        <div className="form-group">
          <label htmlFor="title">{t('improvements.form.title')} *</label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('improvements.form.titlePlaceholder')}
            required
            minLength={5}
            maxLength={200}
          />
        </div>

        {/* Type & Priority */}
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="type">{t('improvements.form.type')}</label>
            <select
              id="type"
              value={type}
              onChange={(e) => setType(e.target.value as EnhancementType | '')}
            >
              <option value="">{t('improvements.form.typePlaceholder')}</option>
              {['feature', 'bug_fix', 'improvement', 'refactor', 'documentation', 'security', 'performance'].map(
                (t_type) => (
                  <option key={t_type} value={t_type}>
                    {t(`improvements.types.${t_type}`)}
                  </option>
                )
              )}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="priority">{t('improvements.form.priority')}</label>
            <select
              id="priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value as EnhancementPriority | '')}
            >
              <option value="">{t('improvements.form.priorityPlaceholder')}</option>
              {['critical', 'high', 'medium', 'low'].map((p) => (
                <option key={p} value={p}>
                  {t(`improvements.priority.${p}`)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Description */}
        <div className="form-group">
          <label htmlFor="description">{t('improvements.form.description')} *</label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('improvements.form.descriptionPlaceholder')}
            required
            minLength={20}
            rows={8}
          />
        </div>

        {/* Attachments */}
        <div className="form-group">
          <label>{t('improvements.form.attachments')}</label>
          <div
            className="file-drop-zone"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={32} />
            <p>{t('improvements.form.attachmentsHint')}</p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              style={{ display: 'none' }}
            />
          </div>

          {files.length > 0 && (
            <div className="file-list">
              {files.map((uploadedFile, index) => (
                <div key={index} className="file-item">
                  {uploadedFile.preview ? (
                    <img src={uploadedFile.preview} alt="" className="file-preview" />
                  ) : (
                    <div className="file-icon">{getFileIcon(uploadedFile.file)}</div>
                  )}
                  <div className="file-info">
                    <span className="file-name">{uploadedFile.file.name}</span>
                    <span className="file-size">{formatFileSize(uploadedFile.file.size)}</span>
                  </div>
                  <button
                    type="button"
                    className="btn-remove"
                    onClick={() => removeFile(index)}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* AI Note */}
        <div className="ai-note">
          <Bot size={20} />
          <p>{t('improvements.form.aiNote')}</p>
        </div>

        {/* Error */}
        {error && <div className="error-message">{error}</div>}

        {/* Actions */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => navigate('/improvements')}
          >
            {t('improvements.form.cancel')}
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={isSubmitting || !title || !description}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={18} className="spinning" />
                {t('common.loading')}
              </>
            ) : (
              <>
                <Send size={18} />
                {t('improvements.form.submit')}
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SubmitImprovementPage;
