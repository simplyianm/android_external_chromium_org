// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_EXTENSIONS_ACTIVE_SCRIPT_CONTROLLER_H_
#define CHROME_BROWSER_EXTENSIONS_ACTIVE_SCRIPT_CONTROLLER_H_

#include <map>
#include <set>
#include <string>
#include <vector>

#include "base/callback.h"
#include "base/compiler_specific.h"
#include "base/memory/linked_ptr.h"
#include "chrome/browser/extensions/location_bar_controller.h"
#include "content/public/browser/web_contents_observer.h"

namespace content {
class WebContents;
}

namespace IPC {
class Message;
}

class ExtensionAction;

namespace extensions {
class Extension;

// The provider for ExtensionActions corresponding to scripts which are actively
// running or need permission.
// TODO(rdevlin.cronin): This isn't really a controller, but it has good parity
// with PageAction"Controller".
class ActiveScriptController : public LocationBarController::ActionProvider,
                               public content::WebContentsObserver {
 public:
  explicit ActiveScriptController(content::WebContents* web_contents);
  virtual ~ActiveScriptController();

  // Returns the ActiveScriptController for the given |web_contents|, or NULL
  // if one does not exist.
  static ActiveScriptController* GetForWebContents(
      content::WebContents* web_contents);

  // Returns true if the extension requesting script injection requires
  // user consent. If this is true, the caller should then register a request
  // via RequestScriptInjection().
  bool RequiresUserConsentForScriptInjection(const Extension* extension);

  // Register a request for a script injection, to be executed by running
  // |callback|. The only assumption that can be made about when (or if)
  // |callback| is run is that, if it is run, it will run on the current page.
  void RequestScriptInjection(const Extension* extension,
                              int page_id,
                              const base::Closure& callback);

  // Notifies the ActiveScriptController that an extension has been granted
  // active tab permissions. This will run any pending injections for that
  // extension.
  void OnActiveTabPermissionGranted(const Extension* extension);

  // Notifies the ActiveScriptController of detected ad injection.
  void OnAdInjectionDetected(const std::set<std::string>& ad_injectors);

  // LocationBarControllerProvider implementation.
  virtual ExtensionAction* GetActionForExtension(
      const Extension* extension) OVERRIDE;
  virtual LocationBarController::Action OnClicked(
      const Extension* extension) OVERRIDE;
  virtual void OnNavigated() OVERRIDE;
  virtual void OnExtensionUnloaded(const Extension* extension) OVERRIDE;

 private:
  // A single pending request. This could be a pair, but we'd have way too many
  // stl typedefs, and "request.closure" is nicer than "request.first".
  struct PendingRequest {
    PendingRequest();  // For STL.
    PendingRequest(const base::Closure& closure, int page_id);
    ~PendingRequest();

    base::Closure closure;
    int page_id;
  };
  typedef std::vector<PendingRequest> PendingRequestList;
  typedef std::map<std::string, PendingRequestList> PendingRequestMap;

  // Runs any pending injections for the corresponding extension.
  void RunPendingForExtension(const Extension* extension);

  // Handle the RequestContentScriptPermission message.
  void OnRequestContentScriptPermission(const std::string& extension_id,
                                        int page_id,
                                        int request_id);

  // Grants permission for the given request to run.
  void GrantContentScriptPermission(int request_id);

  // content::WebContentsObserver implementation.
  virtual bool OnMessageReceived(const IPC::Message& message) OVERRIDE;

  // Log metrics.
  void LogUMA() const;

  // Whether or not the ActiveScriptController is enabled (corresponding to the
  // kActiveScriptEnforcement switch). If it is not, it acts as an empty shell,
  // always allowing scripts to run and never displaying actions.
  bool enabled_;

  // The map of extension_id:pending_request of all pending requests.
  PendingRequestMap pending_requests_;

  // The extensions which have been granted permission to run on the given page.
  // TODO(rdevlin.cronin): Right now, this just keeps track of extensions that
  // have been permitted to run on the page via this interface. Instead, it
  // should incorporate more fully with ActiveTab.
  std::set<std::string> permitted_extensions_;

  // Script badges that have been generated for extensions. This is both those
  // with actions already declared that are copied and normalised, and actions
  // that get generated for extensions that haven't declared anything.
  typedef std::map<std::string, linked_ptr<ExtensionAction> > ActiveScriptMap;
  ActiveScriptMap active_script_actions_;

  DISALLOW_COPY_AND_ASSIGN(ActiveScriptController);
};

}  // namespace extensions

#endif  // CHROME_BROWSER_EXTENSIONS_ACTIVE_SCRIPT_CONTROLLER_H_
