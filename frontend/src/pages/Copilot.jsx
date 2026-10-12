import React, { useState, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Brain, Send, ChevronDown, ChevronUp, CheckCircle2, Circle, ArrowRight, CheckSquare } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { motion } from 'framer-motion'

const initialCopilotMessages = [
  {
    id: 'copilot-1',
    sender_type: 'user',
    sender_name: 'You',
    content: 'Draft a technical milestone plan for our upcoming release and break down priority tasks.',
    created_at: new Date(Date.now() - 1800000).toISOString()
  },
  {
    id: 'copilot-2',
    sender_type: 'agent',
    sender_name: 'Project Copilot Synthesis',
    run_id: 'run-9082',
    content: `### Release Milestone Execution Roadmap

Based on indexed workspace architecture documents, here is the verified task breakdown for the upcoming sprint:

1. **WebSocket Authentication & Handshake Middleware**
   - Implement HMAC signature validation on initial socket connection.
   - Enforce rate-limiting of 100 frames/sec per client ID.

2. **Isolated Vector RAG Query Router**
   - Direct user queries to workspace-scoped vector collection.
   - Apply cosine similarity threshold ($\geq 0.78$) for document chunk retrieval.

3. **Critic Validation Loop Integration**
   - Run secondary verification pass over generated outputs prior to workspace broadcast.
`,
    created_at: new Date(Date.now() - 900000).toISOString()
  }
]

const Copilot = () => {
  const { id = 'demo-workspace' } = useParams()
  const [messages, setMessages] = useState(initialCopilotMessages)
  const [query, setQuery] = useState('')
  const [activeRunId, setActiveRunId] = useState(null)
  
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!query.trim()) return

    const userQuery = query
    setQuery('')
    
    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        sender_type: 'user',
        sender_name: 'You',
        content: userQuery,
        created_at: new Date().toISOString()
      }
    ])
    
    setTimeout(scrollToBottom, 50)
    setActiveRunId(`run-${Date.now()}`)

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `copilot-${Date.now()}`,
          sender_type: 'agent',
          sender_name: 'Project Copilot Synthesis',
          run_id: `run-${Date.now()}`,
          content: `### Copilot Plan Synthesis\n\nAnalyzed query: **"${userQuery}"**\n\n- **Validated Sources:** 2 workspace documents cited.\n- **Action Items Created:** Tasks synced to Kanban board.`,
          created_at: new Date().toISOString()
        }
      ])
      setActiveRunId(null)
      setTimeout(scrollToBottom, 50)
    }, 2200)
  }

  const handlePromptSuggestion = (promptText) => {
    setQuery(promptText)
  }

  const stepsList = ['router', 'research', 'planner', 'critic', 'docs', 'finalize']

  return (
    <div className="absolute inset-0 flex flex-col bg-[#F8F8F6] text-[#18181B] h-full overflow-hidden">
      {/* Messages Viewport */}
      <div className="flex-grow overflow-y-auto px-4 py-5 sm:px-8 sm:py-6 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 sm:p-8 select-none max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-[#F4F4F2] border border-[#E4E4E0] flex items-center justify-center text-[#18181B] mb-4 shadow-xs">
              <Brain className="w-6 h-6" />
            </div>
            <h3 className="font-display font-bold text-lg text-[#18181B]">Project Copilot</h3>
            <p className="text-[#71717A] text-xs mt-1.5 max-w-sm leading-relaxed">
              Autonomous multi-agent orchestration. Ask complex questions, request sprint breakdowns, or let agents synthesize living documentation.
            </p>

            {/* Quick Prompts */}
            <div className="mt-6 w-full flex flex-col gap-2">
              <div className="text-[11px] font-semibold text-[#71717A] uppercase tracking-wider">
                Suggested Prompts
              </div>
              <div className="flex flex-col gap-2">
                {[
                  "Draft a technical milestone plan for our upcoming release",
                  "Synthesize key insights and action items from indexed documents",
                  "Break down high-priority tasks and assign recommended owners"
                ].map((promptText, i) => (
                  <button
                    key={i}
                    onClick={() => handlePromptSuggestion(promptText)}
                    className="p-3 bg-white border border-[#E4E4E0] rounded-xl text-left hover:border-[#18181B] hover:bg-[#E7F0E9]/60 hover:shadow-xs transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <span className="text-xs text-[#27272A] font-medium group-hover:text-[#18181B] truncate">
                      {promptText}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 text-[#71717A] group-hover:text-[#18181B] group-hover:translate-x-0.5 transition-all shrink-0 ml-2" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="w-full space-y-5">
            {messages.map((msg) => {
              const isMe = msg.sender_type === 'user'
              if (isMe) {
                return (
                  <motion.div 
                    key={msg.id} 
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15 }}
                    className="flex flex-col items-end space-y-1"
                  >
                    <span className="text-[11px] text-[#71717A] font-mono select-none px-1">{msg.sender_name}</span>
                    <div className="bg-[#18181B] text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs sm:text-sm max-w-[85%] sm:max-w-[70%] leading-relaxed whitespace-pre-wrap select-text shadow-xs">
                      {msg.content}
                    </div>
                  </motion.div>
                )
              } else {
                return (
                  <CopilotAnswerCard key={msg.id} message={msg} workspaceId={id} />
                )
              }
            })}
          </div>
        )}

        {/* Polling live pipeline strip */}
        {activeRunId && (
          <motion.div 
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full bg-white border border-[#E4E4E0] rounded-2xl p-4 sm:p-5 shadow-xs space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#F4F4F2] pb-2.5 select-none">
              <span className="text-xs font-semibold text-[#18181B] flex items-center space-x-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#18181B] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[#18181B]"></span>
                </span>
                <span>Multi-Agent Orchestration Pipeline</span>
              </span>
              <span className="text-[11px] font-semibold text-[#18181B] bg-[#F4F4F2] border border-[#E4E4E0] px-2 py-0.5 rounded-full">
                Running step: critic
              </span>
            </div>
            
            {/* Live Pipeline Strip */}
            <div className="flex items-center justify-between py-2 select-none overflow-x-auto gap-2">
              {stepsList.map((step, index) => {
                const isDone = index < 3
                const isRunning = index === 3
                
                return (
                  <React.Fragment key={step}>
                    <div className="flex flex-col items-center space-y-1 shrink-0 min-w-[52px]">
                      <div className="flex items-center justify-center">
                        {isDone ? (
                          <div className="w-6 h-6 rounded-full bg-[#F0FDF4] border border-[#DCFCE7] flex items-center justify-center">
                            <CheckCircle2 className="w-4 h-4 text-[#15803D]" />
                          </div>
                        ) : isRunning ? (
                          <div className="w-6 h-6 rounded-full bg-[#F4F4F2] border border-[#E4E4E0] flex items-center justify-center">
                            <span className="w-3.5 h-3.5 rounded-full border-2 border-[#18181B] border-t-transparent animate-spin"></span>
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-[#F8F8F6] border border-[#E4E4E0] flex items-center justify-center">
                            <Circle className="w-3 h-3 text-[#A1A1AA]" />
                          </div>
                        )}
                      </div>
                      <span className={`text-[10px] sm:text-[11px] font-semibold capitalize ${isRunning ? 'text-[#18181B]' : isDone ? 'text-[#15803D]' : 'text-[#71717A]'}`}>
                        {step}
                      </span>
                    </div>
                    {index < stepsList.length - 1 && (
                      <div className={`flex-1 h-0.5 min-w-[12px] transition-colors ${isDone ? 'bg-[#15803D]' : isRunning ? 'bg-[#18181B]' : 'bg-[#E4E4E0]'}`}></div>
                    )}
                  </React.Fragment>
                )
              })}
            </div>
          </motion.div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Composer Input Area */}
      <div className="p-3 sm:p-4 bg-white/95 backdrop-blur-md border-t border-[#E4E4E0] select-none shrink-0">
        <div className="w-full">
          <form 
            onSubmit={handleSubmit} 
            className="flex items-center space-x-2 bg-white border border-[#E4E4E0] hover:border-[#18181B] focus-within:border-[#18181B] focus-within:ring-2 focus-within:ring-[#18181B]/10 rounded-xl px-3 py-1.5 transition-all shadow-xs"
          >
            <input 
              type="text"
              required
              value={query}
              disabled={!!activeRunId}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={activeRunId ? "Copilot agents orchestrating answer..." : "Ask Copilot for planning, roadmap breakdown, or knowledge query..."}
              className="flex-grow bg-transparent text-[#18181B] text-xs sm:text-sm focus:outline-none placeholder:text-[#A1A1AA] py-1.5 disabled:opacity-50 min-w-0"
            />
            <button 
              type="submit"
              disabled={!!activeRunId || !query.trim()}
              className="w-8 h-8 rounded-lg bg-[#18181B] text-white hover:bg-[#27272A] disabled:opacity-30 disabled:hover:bg-[#18181B] flex items-center justify-center transition-all active:scale-95 shadow-xs shrink-0 cursor-pointer"
              title="Execute Copilot Run"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
          <div className="flex items-center justify-between text-[10px] text-[#71717A] mt-1.5 px-1 font-mono">
            <span>Verified by multi-agent critic loop</span>
            <span className="hidden sm:inline">Structured output with citation trace</span>
          </div>
        </div>
      </div>
    </div>
  )
}

const CopilotAnswerCard = ({ message, workspaceId }) => {
  const [expandedTrace, setExpandedTrace] = useState(false)

  const sampleTrace = [
    { step: 1, agent: 'ROUTER', provider: 'Gemini', model: '3.6 Flash', latency_ms: 210, output_summary: 'Target route identified: Milestone & Technical RAG' },
    { step: 2, agent: 'RESEARCH', provider: 'Vector RAG', model: 'Embedding-004', latency_ms: 450, output_summary: 'Fetched 4 context chunks from system_architecture.pdf' },
    { step: 3, agent: 'PLANNER', provider: 'Gemini', model: '3.1 Pro', latency_ms: 580, output_summary: 'Generated 3 sub-tasks with estimated story points' },
    { step: 4, agent: 'CRITIC', provider: 'Validator', model: 'Rule-Engine', latency_ms: 320, output_summary: 'Verdict: APPROVED. All citations match workspace files.' }
  ]

  return (
    <motion.div 
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className="w-full bg-white border border-[#E4E4E0] border-l-[3px] border-l-[#18181B] rounded-2xl p-4 sm:p-5 shadow-xs space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#F4F4F2] pb-3 select-none">
        <div className="flex items-center space-x-2.5">
          <div className="w-6 h-6 rounded-lg bg-[#18181B] flex items-center justify-center text-white shrink-0">
            <Brain className="w-3.5 h-3.5" />
          </div>
          <h4 className="font-display font-bold text-xs text-[#18181B] truncate">{message.sender_name}</h4>
          <span className="hidden sm:inline-block text-[10px] bg-[#F4F4F2] text-[#52525B] border border-[#E4E4E0] px-2 py-0.2 rounded font-mono font-medium">
            Orchestrated Plan
          </span>
        </div>
        <div className="text-[10px] font-mono text-[#15803D] bg-[#F0FDF4] border border-[#DCFCE7] px-2 py-0.5 rounded font-medium shrink-0">
          Critic Approved
        </div>
      </div>

      {/* Answer Body */}
      <div className="chat-markdown select-text pl-1 overflow-x-auto">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            table: ({ node, ...props }) => (
              <div className="chat-markdown-table-wrap">
                <table {...props} />
              </div>
            ),
            th: ({ node, ...props }) => <th className="chat-markdown-th" {...props} />,
            td: ({ node, ...props }) => <td className="chat-markdown-td" {...props} />
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>

      {/* Trace Toggler */}
      <div className="pt-3 border-t border-[#F4F4F2] select-none">
        <div className="flex items-center justify-between">
          <button 
            onClick={() => setExpandedTrace(!expandedTrace)}
            className="flex items-center space-x-1.5 text-xs text-[#18181B] font-semibold hover:text-[#365742] focus:outline-none cursor-pointer"
          >
            {expandedTrace ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            <span>Agent Execution Telemetry</span>
          </button>
          
          <span className="text-[10px] text-[#71717A] bg-[#F4F4F2] border border-[#E4E4E0] px-2 py-0.5 rounded font-medium">
            Refined once by Critic Agent
          </span>
        </div>

        {/* Trace details accordion list */}
        {expandedTrace && (
          <div className="mt-3 space-y-2.5 pl-3 border-l-2 border-[#E4E4E0]">
            {sampleTrace.map((step, idx) => (
              <div key={idx} className="space-y-1 font-mono text-xs text-[#52525B] bg-[#F8F8F6] border border-[#E4E4E0] rounded-xl p-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[#18181B] font-bold">Step {step.step}: {step.agent}</span>
                  <span className="text-[10px] bg-white border border-[#E4E4E0] px-1.5 py-0.5 rounded text-[#71717A]">
                    {step.provider} · {step.model} · {(step.latency_ms/1000).toFixed(1)}s
                  </span>
                </div>
                <pre className="bg-[#18181B] text-[#F4F4F5] p-2 rounded-lg border border-[#27272A] overflow-x-auto text-[10px] font-mono leading-relaxed select-text mt-1">
                  {step.output_summary}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Telemetry info strip */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-[#71717A] select-none bg-[#F8F8F6] border border-[#E4E4E0] px-3 py-2 rounded-lg font-sans gap-2">
        <div className="flex items-center space-x-3">
          <span>Latency: <strong className="text-[#18181B]">1.56s</strong></span>
          <span>Tokens: <strong className="text-[#18181B]">1,240</strong></span>
        </div>
        <Link to={`/w/${workspaceId}/tasks`} className="text-[#18181B] hover:text-[#365742] font-semibold flex items-center space-x-1">
          <CheckSquare className="w-3.5 h-3.5 inline" />
          <span>View Tasks Board →</span>
        </Link>
      </div>
    </motion.div>
  )
}

export default Copilot
