import { useState, useCallback } from 'react'
import axios from 'axios'
import { useDropzone } from 'react-dropzone'
import './App.css'

const API_URL = 'http://localhost:8000'

function App() {
  const [files, setFiles] = useState([])
  const [method, setMethod] = useState('ocr')
  const [ocrOptions, setOcrOptions] = useState({
    outputFormat: 'pdf',
    pageRange: ''
  })
  const [shrilipiOptions, setShrilipiOptions] = useState({
    outputFormat: 'txt',
    preserveFormatting: false
  })
  const [results, setResults] = useState([])

  const onDrop = useCallback((acceptedFiles) => {
    const newFiles = acceptedFiles.map(file => ({
      file,
      id: `${file.name}-${Date.now()}`,
      name: file.name,
      size: (file.size / (1024 * 1024)).toFixed(1) + ' MB',
      pages: '-',
      status: 'ready',
      taskId: null
    }))
    setFiles(prev => [...prev, ...newFiles])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true
  })

  const removeFile = (id) => {
    setFiles(prev => prev.filter(f => f.id !== id))
  }

  const clearAll = () => {
    setFiles([])
  }

  const processFiles = async () => {
    const readyFiles = files.filter(f => f.status === 'ready')

    for (const fileItem of readyFiles) {
      try {
        // Update status to processing
        setFiles(prev => prev.map(f =>
          f.id === fileItem.id ? { ...f, status: 'processing' } : f
        ))

        const formData = new FormData()
        formData.append('file', fileItem.file)
        formData.append('mode', method)

        const response = await axios.post(`${API_URL}/upload`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })

        const taskId = response.data.task_id

        // Add to results and start polling
        setResults(prev => [...prev, {
          id: fileItem.id,
          name: fileItem.name,
          taskId,
          status: 'processing',
          progress: 0,
          message: 'Starting...',
          pdfPath: null,
          docxPath: null,
          fileSize: null
        }])

        // Remove from files list
        setFiles(prev => prev.filter(f => f.id !== fileItem.id))

        // Start polling for this task
        pollStatus(taskId, fileItem.id)

      } catch (err) {
        console.error(err)
        setFiles(prev => prev.map(f =>
          f.id === fileItem.id ? { ...f, status: 'error' } : f
        ))
      }
    }
  }

  const pollStatus = (taskId, fileId) => {
    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_URL}/status/${taskId}`)
        const data = response.data

        setResults(prev => prev.map(r => {
          if (r.id !== fileId) return r

          if (data.state === 'SUCCESS') {
            clearInterval(interval)
            return {
              ...r,
              status: 'completed',
              progress: 100,
              message: 'Completed',
              pdfPath: data.result?.pdf_path,
              docxPath: data.result?.docx_path,
              pdfGenerated: data.result?.pdf_generated
            }
          } else if (data.state === 'FAILURE') {
            clearInterval(interval)
            return {
              ...r,
              status: 'error',
              message: data.status || 'Failed'
            }
          } else {
            return {
              ...r,
              progress: data.current || 0,
              message: data.status || 'Processing...'
            }
          }
        }))
      } catch (err) {
        console.error(err)
      }
    }, 2000)
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
          <button className="help-btn">?</button>
        </div>
      </header>

      <main className="main">
        {/* Dropzone */}
        <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
          <input {...getInputProps()} />
          <div className="dropzone-content">
            <div className="cloud-icon">☁️</div>
            <p className="dropzone-text">Drop Gujarati PDFs here</p>
            <button className="browse-btn" onClick={(e) => e.stopPropagation()}>
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
                    <td>{getStatusBadge(file.status)}</td>
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
            <a href="#" className="help-link">Not sure which to choose? ↗</a>
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

                  <div className="option-group toggle-option">
                    <label>Preserve formatting</label>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={shrilipiOptions.preserveFormatting}
                        onChange={(e) => setShrilipiOptions({ ...shrilipiOptions, preserveFormatting: e.target.checked })}
                      />
                      <span className="slider"></span>
                    </label>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="action-buttons">
            <button className="preview-btn">Preview first page</button>
            <button
              className="process-btn"
              disabled={files.length === 0}
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
                        {result.pdfGenerated && (
                          <a
                            href={`${API_URL}/download/${result.taskId}/pdf`}
                            className="download-btn primary"
                            target="_blank"
                            rel="noreferrer"
                            download
                          >
                            ⬇ PDF
                          </a>
                        )}
                        <a
                          href={`${API_URL}/download/${result.taskId}/docx`}
                          className="download-btn secondary"
                          target="_blank"
                          rel="noreferrer"
                          download
                        >
                          📄 DOCX
                        </a>
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
        <p className="footer-note">🔒 Files processed securely; automatically deleted after 1 hour.</p>
      </main>
    </div>
  )
}

export default App
