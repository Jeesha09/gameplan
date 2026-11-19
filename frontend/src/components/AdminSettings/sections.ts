export type AdminSettingType =
  | 'switch'
  | 'number'
  | 'text'
  | 'textarea'
  | 'list'
  | 'select'
  | 'multiselect'
  | 'communities'
  | 'password'
  | 'image'
  | 'emojis'

export interface AdminSetting {
  key: string
  label: string
  type: AdminSettingType
  default: string | number | boolean | string[]
  description?: string
  options?: string[]
  placeholder?: string
  parent?: string
  wide?: boolean
}

export interface AdminSettingGroup {
  heading?: string
  title?: string
  layout?: 'fields'
  settings: AdminSetting[]
}

export interface AdminSection {
  id: string
  label: string
  icon: string
  keywords?: string
  groups: AdminSettingGroup[]
}

const roles = ['Admins only', 'Community admins and up', 'Community staff and up', 'All members']
const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const fileTypes = [
  'jpg',
  'jpeg',
  'png',
  'gif',
  'webp',
  'svg',
  'pdf',
  'mp4',
  'mov',
  'zip',
  'csv',
  'xlsx',
  'docx',
  'txt',
  'json',
]
const pages = ['None', 'Community guidelines', 'Terms of service', 'Privacy policy']

export const postingLimitPrefix = 'posting_limits_'

function postingLimit(field: string, label: string, parent: string): AdminSetting {
  return {
    key: postingLimitPrefix + field,
    label,
    type: 'number',
    default: 0,
    parent: postingLimitPrefix + parent,
  }
}

export const adminSections: AdminSection[] = [
  {
    id: 'site',
    label: 'Site',
    icon: 'lucide-globe',
    groups: [
      {
        heading: 'General',
        layout: 'fields',
        settings: [
          { key: 'site_name', label: 'Site name', type: 'text', default: 'Frappe Forum' },
          {
            key: 'contact_email',
            label: 'Contact email',
            type: 'text',
            default: '',
            placeholder: 'team@example.com',
          },
          {
            key: 'site_description',
            label: 'Short description',
            type: 'text',
            default: 'Forum for Frappe and ERPNext community',
            wide: true,
          },
        ],
      },
      {
        title: 'Logos',
        settings: [
          {
            key: 'logo',
            label: 'Logo',
            type: 'image',
            default: '',
            description: 'Shown in the sidebar and on the login page',
          },
          {
            key: 'logo_dark',
            label: 'Logo for dark mode',
            type: 'image',
            default: '',
            description: 'Used on dark backgrounds. Falls back to the main logo',
          },
          {
            key: 'favicon',
            label: 'Favicon',
            type: 'image',
            default: '',
            description: 'The icon in the browser tab. Square, at least 192 px',
          },
        ],
      },
      {
        heading: 'Access & signup',
        settings: [
          {
            key: 'public_access',
            label: 'Public access',
            type: 'switch',
            default: false,
            description: 'Anyone can read public Spaces without signing in',
          },
          {
            key: 'signup',
            label: 'Who can join',
            type: 'select',
            default: 'Anyone can sign up',
            options: ['Anyone can sign up', 'Invite only'],
            description: 'Invite only hides the sign-up form',
          },
          {
            key: 'invite_expiry_days',
            label: 'Invitations expire after',
            type: 'number',
            default: 3,
            description: 'Unused invite links stop working after these many days',
          },
          {
            key: 'blocked_email_domains',
            label: 'Blocked email domains',
            type: 'list',
            default: '',
            placeholder: 'One domain per line',
            description: 'Sign-ups from these domains are refused',
          },
        ],
      },
      {
        heading: 'Guidelines & legal',
        settings: [
          {
            key: 'guidelines_page',
            label: 'Community guidelines',
            type: 'select',
            default: 'None',
            options: pages,
            description: 'Linked from the footer and the sign-up form',
          },
          {
            key: 'terms_page',
            label: 'Terms of service',
            type: 'select',
            default: 'None',
            options: pages,
            description: 'People agree to it when they sign up',
          },
          {
            key: 'privacy_page',
            label: 'Privacy policy',
            type: 'select',
            default: 'None',
            options: pages,
            description: 'Linked from the footer and the sign-up form',
          },
        ],
      },
    ],
  },
  {
    id: 'communities',
    label: 'Communities',
    icon: 'lucide-building-2',
    keywords: 'spaces members create new community',
    groups: [],
  },
  {
    id: 'people',
    label: 'Member settings',
    icon: 'lucide-user-cog',
    keywords: 'people users',
    groups: [
      {
        heading: 'New members',
        settings: [
          {
            key: 'default_communities',
            label: 'Default Communities',
            type: 'communities',
            default: [],
            placeholder: 'Pick Communities',
            description:
              'New members join these automatically. Leave empty to join every public Community',
          },
          {
            key: 'default_quick_reactions',
            label: 'Quick reactions',
            type: 'emojis',
            default: [],
            description: 'The set new members start with. They can change their own',
          },
          {
            key: 'onboarding_enabled',
            label: 'Onboarding',
            type: 'switch',
            default: true,
            description: 'Show new members a short welcome tour',
          },
        ],
      },
      {
        heading: 'Accounts & privacy',
        settings: [
          {
            key: 'invite_role',
            label: 'Who can invite people',
            type: 'select',
            default: 'Admins only',
            options: roles,
          },
          {
            key: 'allow_email_change',
            label: 'Change their email',
            type: 'switch',
            default: false,
            description: 'Members can switch the email they sign in with',
          },
          {
            key: 'allow_account_deletion',
            label: 'Delete their account',
            type: 'switch',
            default: false,
            description: 'Their posts stay, shown under a deleted user',
          },
          {
            key: 'account_deletion_max_posts',
            label: 'Post limit',
            description: "Members with this many posts or more can't delete their account",
            type: 'number',
            default: 10,
            parent: 'allow_account_deletion',
          },
          {
            key: 'public_profiles',
            label: 'Public profiles',
            type: 'switch',
            default: false,
            description: 'Signed-out visitors can see member profiles while public access is on',
          },
        ],
      },
      {
        heading: 'Emails & notifications',
        settings: [
          {
            key: 'digests_enabled',
            label: 'Email digests',
            type: 'switch',
            default: true,
            description: 'A summary of unread discussions and popular posts',
          },
          {
            key: 'default_digest_frequency',
            label: 'Default frequency',
            type: 'select',
            default: 'Off',
            options: ['Off', 'Weekly', 'Fortnightly', 'Monthly'],
            description: 'What new members start with',
            parent: 'digests_enabled',
          },
          {
            key: 'default_digest_day',
            label: 'Default day',
            type: 'select',
            default: 'Monday',
            options: days,
            parent: 'digests_enabled',
          },
        ],
      },
      {
        title: 'Notification defaults',
        settings: [
          {
            key: 'default_notification_channel',
            label: 'Where notifications go',
            type: 'select',
            default: 'In-app',
            options: ['In-app', 'Email'],
            description: 'Email sends one batch an hour',
          },
          {
            key: 'default_participation_level',
            label: 'Discussions they take part in',
            type: 'select',
            default: 'Watch',
            options: ['Watch', 'Mentions only'],
            description: 'The bell set when a member starts or replies to a discussion',
          },
        ],
      },
    ],
  },
  {
    id: 'posting',
    label: 'Posting rules',
    icon: 'lucide-pen-line',
    keywords: 'posting limits rate caps',
    groups: [
      {
        settings: [
          {
            key: 'min_title_length',
            label: 'Shortest title (characters)',
            type: 'number',
            default: 0,
            description: '0 turns this off',
          },
          {
            key: 'max_title_length',
            label: 'Longest title (characters)',
            type: 'number',
            default: 0,
            description: '0 turns this off',
          },
          {
            key: 'min_post_length',
            label: 'Shortest post (characters)',
            type: 'number',
            default: 0,
            description: '0 turns this off',
          },
          {
            key: 'allow_duplicate_titles',
            label: 'Duplicate titles',
            type: 'switch',
            default: true,
            description: 'A new discussion can reuse the title of an existing one',
          },
          {
            key: 'posting_limits_enabled',
            label: 'Posting rate',
            type: 'switch',
            default: false,
            description:
              'How many new discussions and replies one account can post. Global admins are exempt. Set a limit to 0 to turn it off',
          },
          postingLimit('discussions_hour', 'Discussions per hour', 'enabled'),
          postingLimit('discussions_day', 'Discussions per 24 hours', 'enabled'),
          postingLimit('replies_hour', 'Replies per hour', 'enabled'),
          postingLimit('replies_day', 'Replies per 24 hours', 'enabled'),
          {
            key: 'posting_limits_caps_enabled',
            label: 'Content caps',
            type: 'switch',
            default: false,
            description:
              'The most links, images, files and mentions one post can include. Community staff are exempt in their own Communities. Set a cap to 0 to turn it off',
          },
          postingLimit('max_links', 'Links per post', 'caps_enabled'),
          postingLimit('max_images', 'Images per post', 'caps_enabled'),
          postingLimit('max_attachments', 'Files and videos per post', 'caps_enabled'),
          postingLimit('max_mentions', 'Mentions per post', 'caps_enabled'),
        ],
      },
      {
        title: 'Files',
        settings: [
          {
            key: 'allowed_file_types',
            label: 'Allowed file types',
            type: 'multiselect',
            default: [],
            placeholder: 'Any file type',
            description: 'Applies to every upload on the site, including the desk',
            options: fileTypes,
          },
          {
            key: 'max_upload_mb',
            label: 'Largest upload (MB)',
            type: 'number',
            default: 25,
          },
        ],
      },
    ],
  },
  {
    id: 'features',
    label: 'Features',
    icon: 'lucide-toggle-right',
    groups: [
      {
        settings: [
          {
            key: 'tags_enabled',
            label: 'Tags',
            type: 'switch',
            default: true,
            description: 'Label discussions and filter by tag',
          },
          {
            key: 'tag_create_role',
            label: 'Who can create new tags',
            type: 'select',
            default: 'All members',
            options: roles,
            description: 'Everyone else picks from existing tags',
            parent: 'tags_enabled',
          },
          {
            key: 'polls_enabled',
            label: 'Polls',
            type: 'switch',
            default: true,
            description: 'Add polls to discussions',
          },
          {
            key: 'direct_messages_enabled',
            label: 'Direct messages',
            type: 'switch',
            default: true,
            description: 'Members still choose whether they receive them',
          },
          {
            key: 'direct_message_role',
            label: 'Who can start a conversation',
            type: 'select',
            default: 'All members',
            options: [
              'All members',
              'Basic trust level and up',
              'Member trust level and up',
              'Community staff and up',
            ],
            parent: 'direct_messages_enabled',
          },
          {
            key: 'everyone_mention_role',
            label: 'Mention everyone',
            type: 'select',
            default: 'All members',
            options: roles,
            description: 'Who can use @everyone to notify every member. New accounts never can',
          },
          {
            key: 'search_enabled',
            label: 'Search',
            type: 'switch',
            default: true,
            description: 'Full-text search across discussions',
          },
        ],
      },
      {
        title: 'Integrations',
        settings: [
          {
            key: 'unsplash_access_key',
            label: 'Unsplash access key',
            type: 'password',
            default: '',
            description: 'Lets people pick cover images from Unsplash',
          },
        ],
      },
    ],
  },
  {
    id: 'badges',
    label: 'Badges',
    icon: 'lucide-medal',
    keywords: 'badges grant revoke award',
    groups: [],
  },
  {
    id: 'users',
    label: 'Manage users',
    icon: 'lucide-users',
    keywords: 'users people members invite roles disable trust levels',
    groups: [],
  },
  {
    id: 'account-restrictions',
    label: 'Restricted accounts',
    icon: 'lucide-shield-ban',
    keywords: 'suspend silence block account',
    groups: [],
  },
]
