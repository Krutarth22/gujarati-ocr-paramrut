export function buildUploadForm(file, method, options) {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', method)
  form.append('output_format', options.outputFormat)
  form.append('page_range', method === 'ocr' ? options.pageRange.trim() : '')
  return form
}
