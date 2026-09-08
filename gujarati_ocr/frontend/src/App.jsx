import { useState, useCallback, useEffect, useRef } from 'react'
import axios from 'axios'
import { useDropzone } from 'react-dropzone'
import { buildUploadForm } from './upload.js'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || '/api'
const errorMessage = err => typeof err.response?.data?.detail === 'string'
  ? err.response.data.detail : 'Request failed. Check your connection and access token.'

function App() {
  const [files, setFiles] = useState([])
  const [method, setMethod] = useState('ocr')
  const [token, setToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submittingRef = useRef(false)
  const timers = useRef(new Set())
  const mounted = useRef(true)
  const [ocrOptions, setOcrOptions] = useState({ outputFormat: 'pdf', pageRange: '' })
  const [shrilipiOptions, setShrilipiOptions] = useState({ outputFormat: 'txt' })
  const [results, setResults] = useState([])

  useEffect(() => {
    mounted.current = true
    const activeTimers = timers.current
    return () => {
      mounted.current = false
      activeTimers.forEach(clearTimeout)
      activeTimers.clear()
    }
  }, [])

  const onDrop = useCallback(acceptedFiles => {
    setFiles(prev => [...prev, ...acceptedFiles.map(file => ({
      file, id: crypto.randomUUID(), name: file.name,
      size: (file.size / 1024 ** 2).toFixed(1) + ' MB', pages: '-', status: 'ready',
    }))])
  }, [])
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, multiple: true,
  })
  const removeFile = id => setFiles(prev => prev.filter(f => f.id !== id))
  const clearAll = () => setFiles([])

  const pollStatus = (taskId, fileId, accessToken, started = Date.now(), failures = 0) => {
    const timer = setTimeout(async () => {
      timers.current.delete(timer)
      if (!mounted.current) return
      try {
        const { data } = await axios.get(`${API_URL}/status/${taskId}`, {
          headers: { Authorization: `Bearer ${accessToken}` }, timeout: 15000,
        })
        if (!mounted.current) return
        const completed = data.state === 'SUCCESS'
        const failed = data.state === 'FAILURE' || data.state === 'REVOKED'
        setResults(prev => prev.map(r => r.id !== fileId ? r : {
          ...r, status: completed ? 'completed' : failed ? 'error' : 'processing',
          progress: completed ? 100 : data.current || 0,
          message: data.status, formats: data.result?.formats || [],
        }))
        if (!completed && !failed) {
          if (Date.now() - started > 45 * 60 * 1000) throw new Error('Job timed out.')
          pollStatus(taskId, fileId, accessToken, started)
        }
      } catch (err) {
        if (!mounted.current) return
        if (failures < 2 && ![401, 404].includes(err.response?.status) && Date.now() - started < 45 * 60 * 1000) {
          pollStatus(taskId, fileId, accessToken, started, failures + 1)
        } else {
          setResults(prev => prev.map(r => r.id !== fileId ? r : {
            ...r, status: 'error', message: errorMessage(err),
          }))
        }
      }
    }, 2000)
    timers.current.add(timer)
  }

  const processFiles = async () => {
    if (submittingRef.current || !token) return
    submittingRef.current = true
    setSubmitting(true)
    try {
      for (const item of files.filter(f => f.status === 'ready')) {
        setFiles(prev => prev.map(f => f.id === item.id ? { ...f, status: 'processing' } : f))
        try {
          const options = method === 'ocr' ? ocrOptions : shrilipiOptions
          const { data } = await axios.post(`${API_URL}/upload`, buildUploadForm(item.file, method, options), {
            headers: { Authorization: `Bearer ${token}` }, timeout: 120000,
          })
          setResults(prev => [...prev, { id: item.id, name: item.name, taskId: data.task_id,
            status: 'processing', progress: 0, message: 'Starting...', formats: [] }])
          setFiles(prev => prev.filter(f => f.id !== item.id))
          pollStatus(data.task_id, item.id, token)
        } catch (err) {
          setFiles(prev => prev.map(f => f.id === item.id ? { ...f, status: 'error', error: errorMessage(err) } : f))
        }
      }
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  const downloadResult = async (result, format) => {
    try {
      const { data } = await axios.get(`${API_URL}/download/${result.taskId}/${format}`, {
        headers: { Authorization: `Bearer ${token}` }, responseType: 'blob', timeout: 120000,
      })
      const url = URL.createObjectURL(data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${result.name.replace(/\.pdf$/i, '')}.${format}`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      setResults(prev => prev.map(r => r.id === result.id
        ? { ...r, downloadError: 'Download failed. Check your token; files may have expired.' } : r))
    }
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'ready': return <span className="badge ready">Ready</span>
      case 'processing': return <span className="badge processing">● Processing</span>
      case 'error': return <span className="badge error">Error</span>
      default: return null
    }
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon">ગુ</span>
          </div>
          <div className="header-text">
            <h1>Gujarati PDF Converter</h1>
            <p>Upload Gujarati PDFs and choose OCR or Shree Lipi conversion.</p>
          </div>
        </div>
        <div className="header-right">
          <span title="Choose OCR for scans or Shree Lipi for legacy font text.">?</span>
        </div>
      </header>

      <main className="main">
        <label className="option-group">
          Access token
          <input type="password" value={token} autoComplete="off"
            onChange={e => setToken(e.target.value)} placeholder="Enter the server access token" />
        </label>
        {/* Dropzone */}
        <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
          <input {...getInputProps()} />
          <div className="dropzone-content">
            <div className="cloud-icon">☁️</div>
            <p className="dropzone-text">Drop Gujarati PDFs here</p>
            <button className="browse-btn" onClick={(e) => { e.stopPropagation(); open() }}>
              Browse files
            </button>
          </div>
        </div>

        {/* Files Table */}
        {files.length > 0 && (
          <div className="files-section">
            <div className="files-header">
              <h3>Files ready for processing ({files.length})</h3>
              <button className="clear-btn" onClick={clearAll}>🗑️ Clear all</button>
            </div>
            <table className="files-table">
              <thead>
                <tr>
                  <th>FILENAME</th>
                  <th>SIZE</th>
                  <th>PAGES</th>
                  <th>STATUS</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {files.map(file => (
                  <tr key={file.id}>
                    <td className="filename">
                      <span className="file-icon">📄</span>
                      {file.name}
                    </td>
                    <td>{file.size}</td>
                    <td>{file.pages}</td>
                    <td>{getStatusBadge(file.status)}{file.error && <span className="error-text">{file.error}</span>}</td>
                    <td>
                      <button className="delete-btn" onClick={() => removeFile(file.id)}>🗑️</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Method Selection */}
        <div className="method-section">
          <div className="method-header">
            <h3>Choose a method</h3>
            <span className="help-link">OCR for scans; Shree Lipi for legacy font text.</span>
          </div>

          <div className="method-cards">
            {/* OCR Card */}
            <div
              className={`method-card ${method === 'ocr' ? 'selected' : ''}`}
              onClick={() => setMethod('ocr')}
            >
              <div className="method-card-header">
                <div className="method-icon ocr-icon">🔍</div>
                <input
                  type="radio"
                  name="method"
                  checked={method === 'ocr'}
                  onChange={() => setMethod('ocr')}
                />
              </div>
              <h4>OCR (Gujarati)</h4>
              <p className="method-desc">Use when PDF is scanned or text is not selectable. Converts images to text.</p>
              <p className="method-time">⏱️ Typical time: 10-60 seconds depending on pages.</p>

              {method === 'ocr' && (
                <div className="method-options">
                  <div className="option-group">
                    <label>Output Format</label>
                    <div className="radio-group">
                      <label className={ocrOptions.outputFormat === 'pdf' ? 'active' : ''}>
                        <input
                          type="radio"
                          name="ocrFormat"
                          value="pdf"
                          checked={ocrOptions.outputFormat === 'pdf'}
                          onChange={(e) => setOcrOptions({ ...ocrOptions, outputFormat: e.target.value })}
                        />
                        Searchable PDF
                      </label>
                      <label className={ocrOptions.outputFormat === 'docx' ? 'active' : ''}>
                        <input
                          type="radio"
                          name="ocrFormat"
                          value="docx"
                          checked={ocrOptions.outputFormat === 'docx'}
                          onChange={(e) => setOcrOptions({ ...ocrOptions, outputFormat: e.target.value })}
                        />
                        Word (.docx)
                      </label>
                    </div>
                  </div>



                  <div className="option-group">
                    <label>Page Range (Optional)</label>
                    <input
                      type="text"
                      placeholder="e.g. 1-5, 8"
                      value={ocrOptions.pageRange}
                      onChange={(e) => setOcrOptions({ ...ocrOptions, pageRange: e.target.value })}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Shrilipi Card */}
            <div
              className={`method-card ${method === 'shrilipi' ? 'selected' : ''}`}
              onClick={() => setMethod('shrilipi')}
            >
              <div className="method-card-header">
                <div className="method-icon shrilipi-icon">અ</div>
                <input
                  type="radio"
                  name="method"
                  checked={method === 'shrilipi'}
                  onChange={() => setMethod('shrilipi')}
                />
              </div>
              <h4>Shree Lipi → Unicode</h4>
              <p className="method-desc">Use when PDF text is selectable but appears garbled (font issue). Converts to readable Unicode.</p>

              {method === 'shrilipi' && (
                <div className="method-options">
                  <div className="option-group">
                    <label>Output Format</label>
                    <div className="radio-group">
                      <label className={shrilipiOptions.outputFormat === 'txt' ? 'active' : ''}>
                        <input
                          type="radio"
                          name="shrilipiFormat"
                          value="txt"
                          checked={shrilipiOptions.outputFormat === 'txt'}
                          onChange={(e) => setShrilipiOptions({ ...shrilipiOptions, outputFormat: e.target.value })}
                        />
                        Unicode Text (.txt)
                      </label>
                      <label className={shrilipiOptions.outputFormat === 'md' ? 'active' : ''}>
                        <input
                          type="radio"
                          name="shrilipiFormat"
                          value="md"
                          checked={shrilipiOptions.outputFormat === 'md'}
                          onChange={(e) => setShrilipiOptions({ ...shrilipiOptions, outputFormat: e.target.value })}
                        />
                        Markdown (.md)
                      </label>
                    </div>
                  </div>


                </div>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="action-buttons">
            <button
              className="process-btn"
              disabled={!files.some(f => f.status === 'ready') || submitting || !token}
              onClick={processFiles}
            >
              Process Files →
            </button>
          </div>
        </div>

        {/* Results Section */}
        {results.length > 0 && (
          <div className="results-section">
            <h3>Results</h3>
            <div className="results-list">
              {results.map(result => (
                <div key={result.id} className={`result-item ${result.status}`}>
                  <div className="result-info">
                    <div className="result-icon">
                      {result.status === 'completed' ? '✅' : '🔄'}
                    </div>
                    <div className="result-details">
                      <span className="result-name">{result.name}</span>
                      {result.status === 'processing' && (
                        <>
                          <div className="result-progress">
                            <div
                              className="result-progress-bar"
                              style={{ width: `${result.progress}%` }}
                            ></div>
                          </div>
                          <span className="result-message">{result.message}</span>
                        </>
                      )}
                      {result.status === 'completed' && result.fileSize && (
                        <span className="result-size">Searchable PDF • {result.fileSize}</span>
                      )}
                    </div>
                  </div>
                  <div className="result-status">
                    {result.status === 'processing' && (
                      <span className="processing-text">Processing...</span>
                    )}
                    {result.status === 'completed' && (
                      <div className="result-actions">
                        {(result.formats || []).map(format => (
                          <button key={format} className="download-btn secondary"
                            onClick={() => downloadResult(result, format)}>
                            Download {format.toUpperCase()}
                          </button>
                        ))}
                        {result.downloadError && <span className="error-text">{result.downloadError}</span>}
                      </div>
                    )}
                    {result.status === 'error' && (
                      <span className="error-text">⚠️ {result.message}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer Note */}
        <p className="footer-note">Files are retained for 24 hours after processing and removed during hourly cleanup. Downloads require your access token.</p>
      </main>
    </div>
  )
}

export default App
