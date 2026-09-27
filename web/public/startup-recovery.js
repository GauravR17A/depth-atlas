// Compatibility bridge for the retired 0.14.1 entry URL reported in production.
// Redirect once before the old app mounts; preserve shared investigation fragments.
(function () {
  var url = new URL(window.location.href);
  var alreadyRetried = url.searchParams.has('_startup_recovered');
  url.searchParams.delete('release');
  url.searchParams.set('_startup_recovered', String(Date.now()));
  if (!alreadyRetried) {
    window.location.replace(url.href);
    return;
  }
  var root = document.getElementById('root') || document.body;
  var panel = document.createElement('main');
  panel.style.cssText = 'min-height:100vh;box-sizing:border-box;padding:32px;background:#0b1621;color:#dceaf0;font:16px/1.6 system-ui,sans-serif';
  var title = document.createElement('h1');
  title.textContent = 'The workspace needs a fresh page';
  var message = document.createElement('p');
  message.textContent = 'An older app page is still being served. Try reloading, or open this link in a new tab.';
  var reload = document.createElement('a');
  reload.textContent = 'Reload workspace';
  reload.href = url.href;
  reload.style.cssText = 'display:inline-block;color:#a1decf;border:1px solid #709f99;padding:10px 16px';
  panel.append(title, message, reload);
  root.replaceChildren(panel);
}());
