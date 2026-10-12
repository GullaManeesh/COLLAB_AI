
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Upload,
  FileText,
  Trash2,
  X,
  AlertCircle,
  CheckCircle,
  LoaderCircle,
} from 'lucide-react'
import api from '../api/client'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'txt', 'md']

function formatSize(bytes = 0) {
  if (!bytes) return '0 Bytes'
  const units = ['Bytes', 'KB', 'MB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  return `${(bytes / 1024 ** index).toFixed(1)} ${units[index]}`
}

function getErrorMessage(error) {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).join(', ')
  }

  return error?.message || 'Something went wrong. Please try again.'
}

function getStatusClasses(status) {
  if (status === 'ready') {
    return 'bg-green-50 text-green-700 border-green-200'
  }
  if (status === 'failed') {
    return 'bg-red-50 text-red-700 border-red-200'
  }
  return 'bg-amber-50 text-amber-700 border-amber-200'
}

export default function Documents() {
  const { id: workspaceId } = useParams()
  const fileInputRef = useRef(null)

  const [documents, setDocuments] = useState([])
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const documentsUrl = `/api/workspaces/${workspaceId}/documents`

  const loadDocuments = useCallback(async () => {
    if (!workspaceId) return

    setLoading(true)
    setError('')

    try {
      const response = await api.get(documentsUrl)
      const items = response.data.documents || []

      setDocuments(items)
      setSelectedDoc((current) => {
        if (!current) return null
        return items.find((doc) => doc.id === current.id) || null
      })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [documentsUrl, workspaceId])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  async function uploadFile(file) {
    if (!file || uploading) return

    setError('')
    setSuccess('')

    const extension = file.name.split('.').pop()?.toLowerCase()

    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setError('Choose a PDF, DOCX, TXT, or MD file.')
      return
    }

    if (file.size === 0) {
      setError('The selected file is empty.')
      return
    }

    if (file.size > MAX_FILE_SIZE) {
      setError('The maximum file size is 10 MB.')
      return
    }

    const formData = new FormData()
    formData.append('file', file)

    setUploading(true)

    try {
      const response = await api.post(documentsUrl, formData, {
        // The API client adds the CSRF header and session cookie.
        // Do not set Content-Type manually; the browser supplies
        // the multipart boundary.
        headers: { 'Content-Type': undefined },
        timeout: 300000,
      })

      const newDocument = response.data

      setDocuments((current) => [
        newDocument,
        ...current.filter((doc) => doc.id !== newDocument.id),
      ])
      setSelectedDoc(newDocument)
      setSuccess(
        `Uploaded and processed ${newDocument.filename}: ${newDocument.chunk_count} chunks stored.`,
      )
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function deleteDocument(document) {
    if (!document || deletingId) return

    const confirmed = window.confirm(
      `Delete "${document.filename}" and all its stored chunks?`,
    )
    if (!confirmed) return

    setDeletingId(document.id)
    setError('')
    setSuccess('')

    try {
      await api.delete(`${documentsUrl}/${document.id}`)

      setDocuments((current) =>
        current.filter((doc) => doc.id !== document.id),
      )
      setSelectedDoc((current) =>
        current?.id === document.id ? null : current,
      )
      setSuccess(`Deleted ${document.filename}.`)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setDeletingId(null)
    }
  }

  function handleDrop(event) {
    event.preventDefault()
    if (uploading) return

    const file = event.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden bg-[#F8F8F6] text-[#18181B]">
      <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
        <div className="mb-6">
          <h2 className="text-lg font-bold tracking-tight sm:text-xl">
            Documents Repository
          </h2>
          <p className="mt-1 text-xs text-[#71717A]">
            Upload workspace documents. CollabAI extracts their text, creates
            chunks and embeddings, and stores them for later retrieval.
          </p>
        </div>

        <div
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`mb-6 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-white p-8 text-center transition ${uploading
            ? 'cursor-wait border-amber-300'
            : 'border-[#E4E4E0] hover:border-[#18181B]'
            }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            disabled={uploading}
            onChange={(event) => uploadFile(event.target.files?.[0])}
          />

          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[#F4F4F2]">
            {uploading ? (
              <LoaderCircle className="h-5 w-5 animate-spin" />
            ) : (
              <Upload className="h-5 w-5" />
            )}
          </div>

          <span className="text-sm font-bold">
            {uploading
              ? 'Uploading, extracting text and generating embeddings...'
              : 'Click or drag a document here'}
          </span>
          <span className="mt-1 text-[11px] text-[#71717A]">
            PDF, DOCX, TXT or MD · Maximum 10 MB
          </span>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 flex items-start gap-2 rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-800">
            <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{success}</span>
          </div>
        )}

        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold">Workspace documents</h3>
          <button
            onClick={loadDocuments}
            disabled={loading || uploading}
            className="rounded-lg border border-[#E4E4E0] bg-white px-3 py-1.5 text-xs hover:bg-[#F4F4F2] disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="py-8 text-center text-sm text-[#71717A]">
            Loading documents...
          </p>
        ) : documents.length === 0 ? (
          <div className="rounded-2xl border border-[#E4E4E0] bg-white p-10 text-center">
            <FileText className="mx-auto mb-3 h-8 w-8 text-[#71717A]" />
            <p className="text-sm font-semibold">No documents uploaded</p>
            <p className="mt-1 text-xs text-[#71717A]">
              Upload a document to start building the workspace knowledge base.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {documents.map((doc) => (
              <button
                type="button"
                key={doc.id}
                onClick={() => setSelectedDoc(doc)}
                className={`flex items-center justify-between gap-3 rounded-xl border bg-white p-4 text-left transition hover:border-[#18181B] ${selectedDoc?.id === doc.id
                  ? 'border-[#18181B] ring-2 ring-black/10'
                  : 'border-[#E4E4E0]'
                  }`}
              >
                <span className="flex min-w-0 items-center gap-3">
                  <FileText className="h-5 w-5 shrink-0" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold">
                      {doc.filename}
                    </span>
                    <span className="mt-1 block text-xs text-[#71717A]">
                      {formatSize(doc.size_bytes)} · {doc.chunk_count || 0} chunks
                    </span>
                  </span>
                </span>

                <span
                  className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold ${getStatusClasses(doc.status)}`}
                >
                  {doc.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </main>

      {selectedDoc && (
        <aside className="fixed inset-y-0 right-0 z-20 flex w-full flex-col overflow-y-auto border-l border-[#E4E4E0] bg-white shadow-xl sm:w-80 lg:static lg:shadow-none">
          <div className="flex items-center justify-between border-b border-[#E4E4E0] p-4">
            <h3 className="truncate pr-3 text-sm font-bold">
              {selectedDoc.filename}
            </h3>
            <button
              onClick={() => setSelectedDoc(null)}
              aria-label="Close document details"
              className="rounded-lg p-1.5 hover:bg-[#F4F4F2]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 space-y-4 p-5">
            <div className="space-y-3 rounded-xl border border-[#E4E4E0] bg-[#F8F8F6] p-4 text-xs">
              <div className="flex justify-between gap-3">
                <span className="text-[#71717A]">File size</span>
                <span className="font-semibold">{formatSize(selectedDoc.size_bytes)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-[#71717A]">Chunks</span>
                <span className="font-semibold">{selectedDoc.chunk_count || 0}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-[#71717A]">Uploaded by</span>
                <span className="font-semibold">
                  {selectedDoc.uploader_name || 'Unknown'}
                </span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-[#71717A]">Status</span>
                <span className="font-semibold">{selectedDoc.status}</span>
              </div>
              {selectedDoc.error && (
                <p className="break-words text-red-700">{selectedDoc.error}</p>
              )}
            </div>

            <p className="text-xs leading-relaxed text-[#71717A]">
              The original document metadata is stored in MongoDB's
              <code> documents </code>
              collection. Extracted text chunks and their embedding vectors are
              stored in
              <code> chunks </code>
              with references to the document, workspace and uploader.
            </p>
          </div>

          <div className="border-t border-[#E4E4E0] p-4">
            <button
              onClick={() => deleteDocument(selectedDoc)}
              disabled={deletingId === selectedDoc.id || uploading}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-red-200 bg-white py-2.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              {deletingId === selectedDoc.id ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete document and chunks
            </button>
          </div>
        </aside>
      )}
    </div>
  )
}
