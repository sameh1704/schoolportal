/**
 * School Portal Admin - View Mode Manager
 * Provides Windows Explorer-like view modes for file/folder listings
 */

(function() {
  'use strict';

  // View mode definitions matching Windows Explorer
  const VIEW_MODES = [
    { id: 'extralarge', name: 'Extra large icons', icon: 'extralarge', cols: 1 },
    { id: 'large', name: 'Large icons', icon: 'large', cols: 1 },
    { id: 'medium', name: 'Medium icons', icon: 'medium', cols: 1 },
    { id: 'small', name: 'Small icons', icon: 'small', cols: 1 },
    { id: 'list', name: 'List', icon: 'list', cols: 1 },
    { id: 'details', name: 'Details', icon: 'details', cols: 4 },
    { id: 'tiles', name: 'Tiles', icon: 'tiles', cols: 1 },
    { id: 'content', name: 'Content', icon: 'content', cols: 3 },
  ];

  // SVG Icons for view mode buttons
  const ICONS = {
    extralarge: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="6" y="6" width="12" height="12" rx="1"/></svg>`,
    large: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="10" height="10" rx="1"/></svg>`,
    medium: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="8" y="8" width="8" height="8" rx="1"/></svg>`,
    small: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>`,
    list: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>`,
    details: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>`,
    tiles: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/></svg>`,
    content: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/><line x1="14" y1="9" x2="21" y2="9"/></svg>`,
  };

  // File type icons
  const FILE_ICONS = {
    folder: '📁',
    pdf: '📄',
    pptx: '📊', ppt: '📊',
    docx: '📝', doc: '📝',
    xlsx: '📊', xls: '📊',
    mp4: '🎬', webm: '🎬', avi: '🎬', mov: '🎬',
    png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼',
    txt: '📄', md: '📄',
    zip: '📦', rar: '📦', '7z': '📦',
    default: '📄',
  };

  function getFileIcon(filename, isDir) {
    if (isDir) return FILE_ICONS.folder;
    const ext = filename.split('.').pop().toLowerCase();
    return FILE_ICONS[ext] || FILE_ICONS.default;
  }

  function formatFileSize(bytes) {
    if (bytes === undefined || bytes === null) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
  }

  function formatDate(dateStr) {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleDateString('ar-SA', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  // ViewModeManager Class
  class ViewModeManager {
    constructor(options = {}) {
      this.container = options.container || document.querySelector('.item-list');
      this.toolbar = options.toolbar || document.querySelector('.view-mode-toolbar');
      this.currentMode = options.defaultMode || 'list';
      this.items = options.items || [];
      this.onModeChange = options.onModeChange || null;
      this.persistKey = options.persistKey || 'admin_view_mode';

      this.init();
    }

    init() {
      if (!this.container) {
        console.warn('ViewModeManager: No container found');
        return;
      }

      this.createToolbar();
      this.loadPersistedMode();
      this.applyMode(this.currentMode);
      this.bindEvents();
    }

    createToolbar() {
      if (this.toolbar) return; // Already exists

      this.toolbar = document.createElement('div');
      this.toolbar.className = 'view-mode-toolbar';
      this.toolbar.innerHTML = this.renderToolbar();
      this.container.parentNode.insertBefore(this.toolbar, this.container);
    }

    renderToolbar() {
      const buttonsHtml = VIEW_MODES.map(mode => `
        <button type="button"
                class="view-mode-btn"
                data-mode="${mode.id}"
                title="${mode.name}"
                aria-label="${mode.name}"
                aria-pressed="${mode.id === this.currentMode}">
          ${ICONS[mode.icon]}
          <span class="view-mode-label">${mode.name}</span>
        </button>
      `).join('');

      return `
        <label for="view-mode-select">طريقة العرض:</label>
        <select id="view-mode-select" class="view-mode-select" aria-label="اختر طريقة العرض">
          ${VIEW_MODES.map(mode => `
            <option value="${mode.id}" ${mode.id === this.currentMode ? 'selected' : ''}>
              ${mode.name}
            </option>
          `).join('')}
        </select>
        <div class="view-mode-buttons" role="group" aria-label="طرق العرض">
          ${buttonsHtml}
        </div>
      `;
    }

    bindEvents() {
      // Select dropdown
      const select = this.toolbar.querySelector('#view-mode-select');
      if (select) {
        select.addEventListener('change', (e) => {
          this.setMode(e.target.value);
        });
      }

      // Button group
      const buttons = this.toolbar.querySelectorAll('.view-mode-btn');
      buttons.forEach(btn => {
        btn.addEventListener('click', () => {
          this.setMode(btn.dataset.mode);
        });
      });

      // Keyboard navigation for button group
      this.toolbar.addEventListener('keydown', (e) => {
        const buttons = Array.from(this.toolbar.querySelectorAll('.view-mode-btn'));
        const activeIndex = buttons.findIndex(b => b.classList.contains('active'));

        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          e.preventDefault();
          const dir = e.key === 'ArrowRight' ? 1 : -1;
          const newIndex = (activeIndex + dir + buttons.length) % buttons.length;
          buttons[newIndex].focus();
          buttons[newIndex].click();
        } else if (e.key === 'Home') {
          e.preventDefault();
          buttons[0].focus();
          buttons[0].click();
        } else if (e.key === 'End') {
          e.preventDefault();
          buttons[buttons.length - 1].focus();
          buttons[buttons.length - 1].click();
        }
      });
    }

    setMode(mode) {
      if (!VIEW_MODES.find(m => m.id === mode)) {
        console.warn(`ViewModeManager: Unknown mode "${mode}"`);
        return;
      }

      this.currentMode = mode;
      this.applyMode(mode);
      this.persistMode(mode);
      this.updateToolbarUI(mode);

      if (this.onModeChange) {
        this.onModeChange(mode);
      }
    }

    applyMode(mode) {
      // Remove all view classes
      VIEW_MODES.forEach(m => {
        this.container.classList.remove(`view-${m.id}`);
      });

      // Add current mode class
      this.container.classList.add(`view-${mode}`);

      // Re-render items if we have item data
      if (this.items.length > 0) {
        this.renderItems();
      }
    }

    renderItems() {
      // This method should be overridden or extended by the consumer
      // to render items based on the current view mode
      if (typeof this.renderItem === 'function') {
        this.container.innerHTML = this.items.map((item, index) =>
          this.renderItem(item, index)
        ).join('');
      }
    }

    updateToolbarUI(mode) {
      // Update select
      const select = this.toolbar.querySelector('#view-mode-select');
      if (select) select.value = mode;

      // Update buttons
      const buttons = this.toolbar.querySelectorAll('.view-mode-btn');
      buttons.forEach(btn => {
        const isActive = btn.dataset.mode === mode;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-pressed', isActive);
      });
    }

    loadPersistedMode() {
      try {
        const saved = localStorage.getItem(this.persistKey);
        if (saved && VIEW_MODES.find(m => m.id === saved)) {
          this.currentMode = saved;
        }
      } catch (e) {
        // localStorage not available
      }
    }

    persistMode(mode) {
      try {
        localStorage.setItem(this.persistKey, mode);
      } catch (e) {
        // localStorage not available
      }
    }

    setItems(items) {
      this.items = items;
      this.renderItems();
    }

    getMode() {
      return this.currentMode;
    }
  }

  // Enhanced version with file/folder data rendering
  class FileBrowserViewModeManager extends ViewModeManager {
    constructor(options = {}) {
      super(options);
      this.foldersFirst = options.foldersFirst !== false;
    }

    renderItem(item, index) {
      const isDir = item.is_dir || item.isDir || false;
      const icon = getFileIcon(item.name, isDir);
      const size = isDir ? '—' : formatFileSize(item.size);
      const modified = formatDate(item.modified || item.mtime);

      const mode = this.currentMode;

      // Common attributes
      const href = item.path || item.url || '#';
      const target = item.target || '_self';
      const rel = target === '_blank' ? 'noopener noreferrer' : '';

      switch (mode) {
        case 'extralarge':
        case 'large':
        case 'medium':
        case 'small':
          return this.renderIconItem(item, icon, isDir, href, target, rel);

        case 'list':
          return this.renderListItem(item, icon, isDir, href, target, rel);

        case 'details':
          return this.renderDetailsItem(item, icon, isDir, size, modified, href, target, rel);

        case 'tiles':
          return this.renderTilesItem(item, icon, isDir, size, modified, href, target, rel);

        case 'content':
          return this.renderContentItem(item, icon, isDir, size, modified, href, target, rel);

        default:
          return this.renderListItem(item, icon, isDir, href, target, rel);
      }
    }

    renderIconItem(item, icon, isDir, href, target, rel) {
      const label = isDir ? 'فتح المجلد' : (item.open_label || 'فتح الملف');
      return `
        <li class="item" data-name="${this.escapeHtml(item.name)}" data-is-dir="${isDir}">
          <a href="${this.escapeHtml(href)}" target="${target}" rel="${rel}" class="item-link">
            <div class="item-icon">${icon}</div>
            <div class="item-name">${this.escapeHtml(item.name)}</div>
          </a>
        </li>
      `;
    }

    renderListItem(item, icon, isDir, href, target, rel) {
      const label = isDir ? 'فتح المجلد' : (item.open_label || 'فتح الملف');
      const mime = item.mime || item.type || (isDir ? 'مجلد' : 'ملف');
      return `
        <li class="item" data-name="${this.escapeHtml(item.name)}" data-is-dir="${isDir}">
          <div class="item-info">
            <div class="item-name">${icon} ${this.escapeHtml(item.name)}</div>
            <div class="item-meta">${this.escapeHtml(mime)}</div>
          </div>
          <div class="item-action">
            <a href="${this.escapeHtml(href)}" target="${target}" rel="${rel}">${label}</a>
          </div>
        </li>
      `;
    }

    renderDetailsItem(item, icon, isDir, size, modified, href, target, rel) {
      const label = isDir ? 'فتح المجلد' : (item.open_label || 'فتح الملف');
      const mime = item.mime || item.type || (isDir ? 'مجلد' : 'ملف');
      return `
        <li class="item" data-name="${this.escapeHtml(item.name)}" data-is-dir="${isDir}">
          <div class="item-name-col">${icon} ${this.escapeHtml(item.name)}</div>
          <div class="item-meta-col">${this.escapeHtml(mime)}</div>
          <div class="item-size-col">${size}</div>
          <div class="item-action-col">
            <a href="${this.escapeHtml(href)}" target="${target}" rel="${rel}">${label}</a>
          </div>
        </li>
      `;
    }

    renderTilesItem(item, icon, isDir, size, modified, href, target, rel) {
      const label = isDir ? 'فتح المجلد' : (item.open_label || 'فتح الملف');
      const mime = item.mime || item.type || (isDir ? 'مجلد' : 'ملف');
      return `
        <li class="item" data-name="${this.escapeHtml(item.name)}" data-is-dir="${isDir}">
          <a href="${this.escapeHtml(href)}" target="${target}" rel="${rel}" class="item-link">
            <div class="item-icon">${icon}</div>
            <div class="item-info">
              <div class="item-name">${this.escapeHtml(item.name)}</div>
              <div class="item-meta">${this.escapeHtml(mime)} ${!isDir ? '• ' + size : ''}</div>
            </div>
          </a>
        </li>
      `;
    }

    renderContentItem(item, icon, isDir, size, modified, href, target, rel) {
      const label = isDir ? 'فتح المجلد' : (item.open_label || 'فتح الملف');
      const mime = item.mime || item.type || (isDir ? 'مجلد' : 'ملف');
      return `
        <li class="item" data-name="${this.escapeHtml(item.name)}" data-is-dir="${isDir}">
          <a href="${this.escapeHtml(href)}" target="${target}" rel="${rel}" class="item-link">
            <div class="item-icon">${icon}</div>
            <div class="item-info">
              <div class="item-name">${this.escapeHtml(item.name)}</div>
              <div class="item-meta">
                <span>النوع: ${this.escapeHtml(mime)}</span>
                ${!isDir ? `<span>الحجم: ${size}</span>` : ''}
                <span>تاريخ التعديل: ${modified}</span>
              </div>
            </div>
            <div class="item-action">
              <button type="button" class="admin-button" onclick="event.preventDefault(); window.location.href='${this.escapeHtml(href)}'">${label}</button>
            </div>
          </a>
        </li>
      `;
    }

    escapeHtml(text) {
      if (text === undefined || text === null) return '';
      return String(text)
        .replace(/&/g, '&')
        .replace(/</g, '<')
        .replace(/>/g, '>')
        .replace(/"/g, '"')
        .replace(/'/g, '&#039;');
    }

    sortItems() {
      this.items.sort((a, b) => {
        const aIsDir = a.is_dir || a.isDir || false;
        const bIsDir = b.is_dir || b.isDir || false;

        if (this.foldersFirst && aIsDir !== bIsDir) {
          return aIsDir ? -1 : 1;
        }

        return (a.name || '').localeCompare(b.name || '', 'ar', { sensitivity: 'base' });
      });
    }

    renderItems() {
      this.sortItems();
      super.renderItems();

      // Add empty state if no items
      if (this.items.length === 0) {
        this.container.innerHTML = '<li class="empty">لا توجد ملفات أو مجلدات في هذا المسار.</li>';
      }
    }
  }

  // Export to global scope
  window.ViewModeManager = ViewModeManager;
  window.FileBrowserViewModeManager = FileBrowserViewModeManager;
  window.VIEW_MODES = VIEW_MODES;
  window.ICONS = ICONS;
  window.getFileIcon = getFileIcon;
  window.formatFileSize = formatFileSize;
  window.formatDate = formatDate;

  // Auto-initialize on DOMContentLoaded for elements with data-view-mode
  document.addEventListener('DOMContentLoaded', () => {
    const containers = document.querySelectorAll('[data-view-mode]');
    containers.forEach(container => {
      const mode = container.dataset.viewMode || 'list';
      const items = JSON.parse(container.dataset.items || '[]');

      if (container.classList.contains('file-browser')) {
        new FileBrowserViewModeManager({
          container: container,
          defaultMode: mode,
          items: items,
        });
      } else {
        new ViewModeManager({
          container: container,
          defaultMode: mode,
          items: items,
        });
      }
    });
  });

})();