import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildUploadForm } from './upload.js'

for (const [method, format, range] of [['ocr', 'docx', '1-3, 8'], ['shrilipi', 'txt', ''], ['shrilipi', 'md', '']]) {
  test(`${method} sends ${format} and page range`, () => {
    const form = buildUploadForm(new Blob(['pdf']), method, { outputFormat: format, pageRange: range })
    assert.equal(form.get('mode'), method)
    assert.equal(form.get('output_format'), format)
    assert.equal(form.get('page_range'), range)
  })
}
