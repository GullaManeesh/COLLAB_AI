/**
 * Workspace invitations and notifications fixtures.
 */
export const INITIAL_WORKSPACE_INVITATIONS = [
  {
    id: 'inv-1',
    type: 'invitation',
    title: 'Workspace Invitation',
    message: 'Maya invited you to join MajorProject / Sprint Launch',
    actor: {
      name: 'Maya Lin',
      avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100&h=100&fit=crop&crop=faces',
      initials: 'ML',
    },
    actionText: 'invited you to join',
    targetName: 'MajorProject / Sprint Launch',
    workspaceId: 'sprint-launch',
    workspaceName: 'MajorProject / Sprint Launch',
    invitationId: 'inv-1',
    createdAt: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15 mins ago
    isRead: false,
    status: 'pending',
  },
  {
    id: 'inv-2',
    type: 'invitation',
    title: 'Workspace Invitation',
    message: 'Alex Rivera invited you to collaborate on Mobile App Revamp',
    actor: {
      name: 'Alex Rivera',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop&crop=faces',
      initials: 'AR',
    },
    actionText: 'invited you to collaborate on',
    targetName: 'Mobile App Revamp',
    workspaceId: 'mobile-app',
    workspaceName: 'Mobile App Revamp',
    invitationId: 'inv-2',
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    isRead: false,
    status: 'pending',
  },
  {
    id: 'inv-3',
    type: 'invitation',
    title: 'Lab Invitation',
    message: 'Dr. Chen added you to AI Agent RAG Lab',
    actor: {
      name: 'Dr. Sarah Chen',
      avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop&crop=faces',
      initials: 'SC',
    },
    actionText: 'invited you to join team lab',
    targetName: 'AI Agent RAG Lab',
    workspaceId: 'ai-research',
    workspaceName: 'AI Agent RAG Lab',
    invitationId: 'inv-3',
    createdAt: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(), // 5 hours ago
    isRead: false,
    status: 'pending',
  },
  {
    id: 'inv-4',
    type: 'invitation',
    title: 'Workspace Shared',
    message: 'David Kim shared Product Architecture & Specs with you',
    actor: {
      name: 'David Kim',
      avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100&h=100&fit=crop&crop=faces',
      initials: 'DK',
    },
    actionText: 'shared access to',
    targetName: 'Product Architecture & Specs',
    workspaceId: 'sprint-launch',
    workspaceName: 'MajorProject / Sprint Launch',
    invitationId: 'inv-4',
    createdAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // yesterday
    isRead: true,
    status: 'accepted',
  },
]

export const SAMPLE_NOTIFICATIONS = INITIAL_WORKSPACE_INVITATIONS
