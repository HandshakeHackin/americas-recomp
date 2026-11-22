#include <charconv>
#include <cstdio>
#include <fstream>
#include <initializer_list>
#include <sstream>
#include <string>
#include <string_view>

static std::string g_table;
static int g_failures = 0;

static int NumberAfter(std::string_view text, const char* key) {
  size_t at = text.find(key);
  if (at == std::string_view::npos) return -1;
  at += std::string_view(key).size();
  int value = -1;
  auto result = std::from_chars(text.data() + at, text.data() + text.size(), value);
  return result.ec == std::errc{} ? value : -1;
}

static int TableSlot(const char* iface, const char* method) {
  std::string key = std::string("\"name\": \"") + iface + "\",";
  size_t begin = g_table.find(key);
  if (begin == std::string::npos || g_table.find(key, begin + key.size()) != std::string::npos) return -1;
  size_t end = g_table.find("\n  }", begin);
  if (end == std::string::npos) return -1;
  std::string_view table(g_table.data() + begin, end - begin);
  key = std::string("\"name\": \"") + method + "\",";
  size_t at = table.find(key);
  if (at == std::string_view::npos || table.find(key, at + key.size()) != std::string_view::npos) return -1;
  size_t methodEnd = table.find('}', at);
  if (methodEnd == std::string_view::npos) return -1;
  std::string_view entry = table.substr(at, methodEnd - at);
  if (entry.find("\"unnamed\": false") == std::string_view::npos) return -1;
  int slot = NumberAfter(entry, "\"slot\": ");
  int count = NumberAfter(table, "\"nslots\": ");
  return slot >= 3 && slot < count ? slot : -1;
}

struct Surface {
  const char* iface;
  std::initializer_list<const char*> methods;
};

static const Surface kSurface[] = {
  {"IXAccessibilityImpl", {
    "XClosedCaptionGetProperties",
    "XClosedCaptionSetEnabled",
    "XHighContrastGetMode",
    "XSpeechToTextSetPositionHint",
    "XSpeechToTextSendString",
    "XSpeechSynthesizerEnumerateInstalledVoices",
    "XSpeechSynthesizerCreate",
    "XSpeechSynthesizerCloseHandle",
    "XSpeechSynthesizerSetDefaultVoice",
    "XSpeechSynthesizerSetCustomVoice",
    "XSpeechSynthesizerCreateStreamFromText",
    "XSpeechSynthesizerCloseStreamHandle",
    "XSpeechSynthesizerGetStreamDataSize",
    "XSpeechSynthesizerGetStreamData",
    "XSpeechToTextBeginHypothesisString",
    "XSpeechToTextUpdateHypothesisString",
    "XSpeechToTextFinalizeHypothesisString",
    "XSpeechToTextCancelHypothesisString",
    "XSpeechSynthesizerCreateStreamFromSsml",
  }},
  {"IXAppCaptureMetadataImpl", {
    "XAppBroadcastIsAppBroadcasting",
    "XAppBroadcastShowUI",
    "XAppBroadcastGetStatus",
    "XAppBroadcastRegisterIsAppBroadcastingChanged",
    "XAppBroadcastUnregisterIsAppBroadcastingChanged",
    "XAppCaptureMetadataAddStringEvent",
    "XAppCaptureMetadataAddInt32Event",
    "XAppCaptureMetadataAddDoubleEvent",
    "XAppCaptureMetadataStartStringState",
    "XAppCaptureMetadataStartInt32State",
    "XAppCaptureMetadataStartDoubleState",
    "XAppCaptureMetadataStopState",
    "XAppCaptureMetadataStopAllStates",
    "XAppCaptureMetadataRemainingStorageBytesAvailable",
    "XAppCaptureRegisterMetadataPurged",
    "XAppCaptureUnRegisterMetadataPurged",
  }},
  {"IXAppCaptureImpl", {
    "XAppCaptureTakeDiagnosticScreenshot",
    "XAppCaptureRecordDiagnosticClip",
    "XAppCaptureTakeScreenshot",
    "XAppCaptureOpenScreenshotStream",
    "XAppCaptureReadScreenshotStream",
    "XAppCaptureCloseScreenshotStream",
    "XAppCaptureEnableRecord",
    "XAppCaptureDisableRecord",
  }},
  {"IXAppCaptureImpl2", {
    "XAppCaptureGetVideoCaptureSettings",
    "XAppCaptureRecordTimespan",
    "XAppCaptureReadLocalStream",
    "XAppCaptureCloseLocalStream",
  }},
  {"IXAppCaptureImpl3", {
    "XAppCaptureStartUserRecord",
    "XAppCaptureStopUserRecord",
  }},
  {"IXAppCaptureImpl4", {
    "XAppCaptureCancelUserRecord",
  }},
  {"IXThreadingImpl", {
    "XAsyncGetStatus",
    "XAsyncGetResultSize",
    "XAsyncCancel",
    "XAsyncRun",
    "XAsyncBegin",
    "XAsyncSchedule",
    "XAsyncComplete",
    "XAsyncGetResult",
    "XTaskQueueCreate",
    "XTaskQueueCreateComposite",
    "XTaskQueueGetPort",
    "XTaskQueueDuplicateHandle",
    "XTaskQueueDispatch",
    "XTaskQueueCloseHandle",
    "XTaskQueueSubmitCallback",
    "XTaskQueueSubmitDelayedCallback",
    "XTaskQueueRegisterWaiter",
    "XTaskQueueUnregisterWaiter",
    "XTaskQueueTerminate",
    "XTaskQueueRegisterMonitor",
    "XTaskQueueUnregisterMonitor",
    "XTaskQueueGetCurrentProcessTaskQueue",
    "XTaskQueueSetCurrentProcessTaskQueue",
    "XThreadSetTimeSensitive",
    "XTaskQueueIsEmpty",
    "XThreadAssertNotTimeSensitive",
    "XThreadIsTimeSensitive",
  }},
  {"IXDisplayImpl", {
    "XDisplayTryEnableHdrMode",
  }},
  {"IXLauncherImpl", {
    "XLaunchUri",
    "XDisplayAcquireTimeoutDeferral",
    "XDisplayCloseTimeoutDeferralHandle",
  }},
  {"IXErrorImpl", {
    "XErrorSetCallback",
    "XErrorSetOptions",
  }},
  {"IXGameImpl", {
    "XGameGetXboxTitleId",
  }},
  {"IXGameImpl2", {
    "XLaunchNewGame",
  }},
  {"IXGameImpl3", {
    "XLaunchRestartOnCrash",
  }},
  {"IXGameActivationImpl", {
    "XGameActivationRegisterForEvent",
    "XGameActivationUnregisterForEvent",
    "XGameActivationAcceptPendingInvite",
  }},
  {"IXGameEventImpl", {
    "XGameEventWrite",
  }},
  {"IXGameInviteImpl", {
    "XGameInviteRegisterForEvent",
    "XGameInviteUnregisterForEvent",
  }},
  {"IXGameInviteImpl2", {
    "XGameInviteRegisterForPendingEvent",
    "XGameInviteUnregisterForPendingEvent",
    "XGameInviteAcceptPendingInvite",
  }},
  {"IXGameProtocolImpl", {
    "XGameProtocolRegisterForActivation",
    "XGameProtocolUnregisterForActivation",
  }},
  {"IXGameRuntimeFeatureImpl", {
    "XGameRuntimeIsFeatureAvailable",
  }},
  {"IXGameSaveImpl", {
    "XGameSaveInitializeProvider",
    "XGameSaveInitializeProviderAsync",
    "XGameSaveInitializeProviderResult",
    "XGameSaveCloseProvider",
    "XGameSaveGetRemainingQuota",
    "XGameSaveGetRemainingQuotaAsync",
    "XGameSaveGetRemainingQuotaResult",
    "XGameSaveDeleteContainer",
    "XGameSaveDeleteContainerAsync",
    "XGameSaveDeleteContainerResult",
    "XGameSaveGetContainerInfo",
    "XGameSaveEnumerateContainerInfo",
    "XGameSaveEnumerateContainerInfoByName",
    "XGameSaveCreateContainer",
    "XGameSaveCloseContainer",
    "XGameSaveEnumerateBlobInfo",
    "XGameSaveEnumerateBlobInfoByName",
    "XGameSaveReadBlobData",
    "XGameSaveReadBlobDataAsync",
    "XGameSaveReadBlobDataResult",
    "XGameSaveCreateUpdate",
    "XGameSaveCloseUpdate",
    "XGameSaveSubmitBlobWrite",
    "XGameSaveSubmitBlobDelete",
    "XGameSaveSubmitUpdate",
    "XGameSaveSubmitUpdateAsync",
    "XGameSaveSubmitUpdateResult",
  }},
  {"IXGameSaveImpl2", {
    "XGameSaveFilesGetFolderWithUiAsync",
    "XGameSaveFilesGetFolderWithUiResult",
    "XGameSaveFilesGetRemainingQuota",
  }},
  {"IXGameStreamingImpl", {
    "XGameStreamingInitialize",
    "XGameStreamingUninitialize",
    "XGameStreamingIsStreaming",
    "XGameStreamingRegisterClientPropertiesChanged",
    "XGameStreamingUnregisterClientPropertiesChanged",
    "XGameStreamingGetStreamPhysicalDimensions",
    "XGameStreamingGetClientCount",
    "XGameStreamingGetClients",
    "XGameStreamingGetConnectionState",
    "XGameStreamingRegisterConnectionStateChanged",
    "XGameStreamingUnregisterConnectionStateChanged",
    "XGameStreamingGetStreamAddedLatency",
    "XGameStreamingGetServerLocationNameSize",
    "XGameStreamingGetServerLocationName",
    "XGameStreamingHideTouchControls",
    "XGameStreamingShowTouchControlLayout",
    "XGameStreamingHideTouchControlsOnClient",
    "XGameStreamingShowTouchControlLayoutOnClient",
    "XGameStreamingIsTouchInputEnabled",
    "XGameStreamingGetLastFrameDisplayed",
    "XGameStreamingGetAssociatedFrame",
    "XGameStreamingGetGamepadPhysicality",
    "XGameStreamingUpdateTouchControlsState",
    "XGameStreamingUpdateTouchControlsStateOnClient",
    "XGameStreamingShowTouchControlsWithStateUpdate",
    "XGameStreamingShowTouchControlsWithStateUpdateOnClient",
    "XGameStreamingGetTouchBundleVersionNameSize",
    "XGameStreamingGetTouchBundleVersion",
    "XGameStreamingGetClientIPAddress",
  }},
  {"IXGameStreamingImpl2", {
    "XGameStreamingGetSessionId",
  }},
  {"IXGameStreamingImpl3", {
    "XGameStreamingGetDisplayDetails",
    "XGameStreamingSetResolution",
  }},
  {"IXGameUiImpl", {
    "XGameUiShowMessageDialogAsync",
    "XGameUiShowMessageDialogResult",
    "XGameUiShowSendGameInviteAsync",
    "XGameUiShowSendGameInviteResult",
    "XGameUiShowPlayerProfileCardAsync",
    "XGameUiShowPlayerProfileCardResult",
    "XGameUiShowAchievementsAsync",
    "XGameUiShowAchievementsResult",
    "XGameUiShowPlayerPickerAsync",
    "XGameUiShowPlayerPickerResultCount",
    "XGameUiShowPlayerPickerResult",
    "XGameUiShowErrorDialogAsync",
    "XGameUiShowErrorDialogResult",
    "XGameUiSetNotificationPositionHint",
    "XGameUiShowTextEntryAsync",
    "XGameUiShowTextEntryResultSize",
    "XGameUiShowTextEntryResult",
    "XGameUiShowWebAuthenticationAsync",
    "XGameUiShowWebAuthenticationResultSize",
    "XGameUiShowWebAuthenticationResult",
    "XGameUiShowWebAuthenticationWithOptionsAsync",
  }},
  {"IXGameUiImpl2", {
    "XGameUiShowMultiplayerActivityGameInviteAsync",
    "XGameUiShowMultiplayerActivityGameInviteResult",
    "XGameUiTextEntryOpen",
    "XGameUiTextEntryClose",
    "XGameUiTextEntryGetState",
    "XGameUiTextEntryGetExtents",
    "XGameUiTextEntryUpdatePositionHint",
    "XGameUiTextEntryUpdateVisibility",
  }},
  {"IXGameUiImpl3", {
    "XGameUiShowStateShareAsync",
    "XGameUiShowStateShareResult",
  }},
  {"IXGameUiImpl4", {
    "XGameUiSetUiCallbacks",
    "XGameUiSetMessageDialogUiResponse",
    "XGameUiSetPlayerPickerUiResponse",
    "XGameUiSetTextEntryUiResponse",
    "XGameUiSetPlayerProfileCardUiResponse",
    "XGameUiSetSendGameInviteUiResponse",
    "XGameUiSetAchievementsUiResponse",
    "XGameUiSetMultiplayerActivityGameInviteUiResponse",
    "XGameUiSetErrorDialogUiResponse",
  }},
  {"IXNetworkingImpl", {
    "XNetworkingQueryPreferredLocalUdpMultiplayerPort",
    "XNetworkingQueryPreferredLocalUdpMultiplayerPortAsync",
    "XNetworkingQueryPreferredLocalUdpMultiplayerPortAsyncResult",
    "XNetworkingRegisterPreferredLocalUdpMultiplayerPortChanged",
    "XNetworkingUnregisterPreferredLocalUdpMultiplayerPortChanged",
    "XNetworkingQuerySecurityInformationForUrlAsync",
    "XNetworkingQuerySecurityInformationForUrlAsyncResultSize",
    "XNetworkingQuerySecurityInformationForUrlAsyncResult",
    "XNetworkingQuerySecurityInformationForUrlUtf16Async",
    "XNetworkingQuerySecurityInformationForUrlUtf16AsyncResultSize",
    "XNetworkingQuerySecurityInformationForUrlUtf16AsyncResult",
    "XNetworkingVerifyServerCertificate",
    "XNetworkingGetConnectivityHint",
    "XNetworkingRegisterConnectivityHintChanged",
    "XNetworkingUnregisterConnectivityHintChanged",
  }},
  {"IXNetworkingImpl2", {
    "XNetworkingQueryConfigurationSetting",
    "XNetworkingSetConfigurationSetting",
    "XNetworkingQueryStatistics",
  }},
  {"IXPackageImpl", {
    "XPackageGetCurrentProcessPackageIdentifier",
    "XPackageIsPackagedProcess",
    "XPackageCreateInstallationMonitor",
    "XPackageCloseInstallationMonitorHandle",
    "XPackageGetInstallationProgress",
    "XPackageUpdateInstallationMonitor",
    "XPackageRegisterInstallationProgressChanged",
    "XPackageUnregisterInstallationProgressChanged",
    "XPackageGetUserLocale",
    "XPackageFindChunkAvailability",
    "XPackageEnumerateChunkAvailability",
    "XPackageChangeChunkInstallOrder",
    "XPackageInstallChunks",
    "XPackageInstallChunksAsync",
    "XPackageInstallChunksResult",
    "XPackageEstimateDownloadSize",
    "XPackageUninstallChunks",
    "XPackageUnregisterPackageInstalled",
    "XPackageGetMountPathSize",
    "XPackageGetMountPath",
    "XPackageCloseMountHandle",
    "XPackageEnumeratePackages",
    "XPackageRegisterPackageInstalled",
    "XPackageGetWriteStats",
    "XPackageUninstallUWPInstance",
    "XPackageEnumerateFeatures",
    "XPackageUninstallPackage",
  }},
  {"IXPackageImpl2", {
    "XPackageEnumeratePackages",
    "XPackageRegisterPackageInstalled",
    "XPackageMountWithUiAsync",
    "XPackageMountWithUiResult",
  }},
  {"IXPackageImpl3", {
    "XPackageEnumeratePackages",
    "XPackageRegisterPackageInstalled",
  }},
  {"IXPackageImpl4", {
    "XPackageGetKind",
  }},
  {"IXPersistentLocalStorageImpl", {
    "XPersistentLocalStorageGetPathSize",
    "XPersistentLocalStorageGetPath",
    "XPersistentLocalStorageGetSpaceInfo",
    "XPersistentLocalStoragePromptUserForSpaceAsync",
    "XPersistentLocalStoragePromptUserForSpaceResult",
  }},
  {"IXPersistentLocalStorageImpl3", {
    "XPersistentLocalStorageMountForPackage",
  }},
  {"IXStoreImpl", {
    "XStoreCreateContext",
    "XStoreCloseContextHandle",
    "XStoreQueryAssociatedProductsAsync",
    "XStoreQueryAssociatedProductsResult",
    "XStoreQueryProductsAsync",
    "XStoreQueryProductsResult",
    "XStoreQueryEntitledProductsAsync",
    "XStoreQueryEntitledProductsResult",
    "XStoreQueryProductForCurrentGameAsync",
    "XStoreQueryProductForCurrentGameResult",
    "XStoreQueryProductForPackageAsync",
    "XStoreQueryProductForPackageResult",
    "XStoreEnumerateProductsQuery",
    "XStoreProductsQueryHasMorePages",
    "XStoreProductsQueryNextPageAsync",
    "XStoreProductsQueryNextPageResult",
    "XStoreCloseProductsQueryHandle",
    "XStoreAcquireLicenseForPackageAsync",
    "XStoreAcquireLicenseForPackageResult",
    "XStoreIsLicenseValid",
    "XStoreCloseLicenseHandle",
    "XStoreCanAcquireLicenseForStoreIdAsync",
    "XStoreCanAcquireLicenseForStoreIdResult",
    "XStoreCanAcquireLicenseForPackageAsync",
    "XStoreCanAcquireLicenseForPackageResult",
    "XStoreQueryGameLicenseAsync",
    "XStoreQueryGameLicenseResult",
    "XStoreQueryAddOnLicensesAsync",
    "XStoreQueryAddOnLicensesResultCount",
    "XStoreQueryAddOnLicensesResult",
    "XStoreQueryConsumableBalanceRemainingAsync",
    "XStoreQueryConsumableBalanceRemainingResult",
    "XStoreReportConsumableFulfillmentAsync",
    "XStoreReportConsumableFulfillmentResult",
    "XStoreGetUserCollectionsIdAsync",
    "XStoreGetUserCollectionsIdResultSize",
    "XStoreGetUserCollectionsIdResult",
    "XStoreGetUserPurchaseIdAsync",
    "XStoreGetUserPurchaseIdResultSize",
    "XStoreGetUserPurchaseIdResult",
    "XStoreQueryLicenseTokenAsync",
    "XStoreQueryLicenseTokenResultSize",
    "XStoreQueryLicenseTokenResult",
    "XStoreShowPurchaseUIAsync",
    "XStoreShowPurchaseUIResult",
    "XStoreShowRateAndReviewUIAsync",
    "XStoreShowRateAndReviewUIResult",
    "XStoreShowRedeemTokenUIAsync",
    "XStoreShowRedeemTokenUIResult",
    "XStoreQueryGameAndDlcPackageUpdatesAsync",
    "XStoreQueryGameAndDlcPackageUpdatesResultCount",
    "XStoreQueryGameAndDlcPackageUpdatesResult",
    "XStoreDownloadPackageUpdatesAsync",
    "XStoreDownloadPackageUpdatesResult",
    "XStoreDownloadAndInstallPackageUpdatesAsync",
    "XStoreDownloadAndInstallPackageUpdatesResult",
    "XStoreDownloadAndInstallPackagesAsync",
    "XStoreDownloadAndInstallPackagesResultCount",
    "XStoreDownloadAndInstallPackagesResult",
    "XStoreQueryPackageIdentifier",
    "XStoreRegisterGameLicenseChanged",
    "XStoreUnregisterGameLicenseChanged",
    "XStoreRegisterPackageLicenseLost",
    "XStoreUnregisterPackageLicenseLost",
  }},
  {"IXStoreImpl2", {
    "XStoreIsAvailabilityPurchasable",
  }},
  {"IXStoreImpl3", {
    "XStoreAcquireLicenseForDurablesAsync",
    "XStoreAcquireLicenseForDurablesResult",
  }},
  {"IXStoreImpl4", {
    "XStoreShowAssociatedProductsUIAsync",
    "XStoreShowAssociatedProductsUIResult",
    "XStoreShowProductPageUIAsync",
    "XStoreShowProductPageUIResult",
  }},
  {"IXStoreImpl5", {
    "XStoreQueryAssociatedProductsForStoreIdAsync",
    "XStoreQueryAssociatedProductsForStoreIdResult",
    "XStoreQueryPackageUpdatesAsync",
    "XStoreQueryPackageUpdatesResultCount",
    "XStoreQueryPackageUpdatesResult",
  }},
  {"IXStoreImpl6", {
    "XStoreShowGiftingUIAsync",
    "XStoreShowGiftingUIResult",
  }},
  {"IXSystemImpl", {
    "XSystemGetConsoleId",
    "XSystemGetXboxLiveSandboxId",
    "XSystemGetAppSpecificDeviceId",
  }},
  {"IXSystemImpl3", {
    "XSystemHandleTrack",
    "XSystemIsHandleValid",
  }},
  {"IXSystemImpl4", {
    "XSystemAllowFullDownloadBandwidth",
  }},
  {"IXSystemAnalyticsImpl", {
    "XSystemGetAnalyticsInfo",
  }},
  {"IXUserImpl", {
    "XUserDuplicateHandle",
    "XUserCloseHandle",
    "XUserCompare",
    "XUserGetMaxUsers",
    "XUserAddAsync",
    "XUserAddResult",
    "XUserGetLocalId",
    "XUserFindUserByLocalId",
    "XUserGetId",
    "XUserFindUserById",
    "XUserGetIsGuest",
    "XUserGetState",
    "XUserGetGamerPictureAsync",
    "XUserGetGamerPictureResultSize",
    "XUserGetGamerPictureResult",
    "XUserGetAgeGroup",
    "XUserCheckPrivilege",
    "XUserResolvePrivilegeWithUiAsync",
    "XUserResolvePrivilegeWithUiResult",
    "XUserGetTokenAndSignatureAsync",
    "XUserGetTokenAndSignatureResultSize",
    "XUserGetTokenAndSignatureResult",
    "XUserGetTokenAndSignatureUtf16Async",
    "XUserGetTokenAndSignatureUtf16ResultSize",
    "XUserGetTokenAndSignatureUtf16Result",
    "XUserResolveIssueWithUiAsync",
    "XUserResolveIssueWithUiResult",
    "XUserResolveIssueWithUiUtf16Async",
    "XUserResolveIssueWithUiUtf16Result",
    "XUserRegisterForChangeEvent",
    "XUserUnregisterForChangeEvent",
    "XUserGetSignOutDeferral",
    "XUserCloseSignOutDeferralHandle",
  }},
  {"IXUserImpl2", {
    "XUserAddByIdWithUiAsync",
    "XUserAddByIdWithUiResult",
  }},
  {"IXUserImpl3", {
    "XUserGetMsaTokenSilentlyAsync",
    "XUserGetMsaTokenSilentlyResult",
    "XUserGetMsaTokenSilentlyResultSize",
  }},
  {"IXUserImpl4", {
    "XUserIsStoreUser",
  }},
  {"IXUserImpl5", {
    "XUserPlatformRemoteConnectSetEventHandlers",
    "XUserPlatformRemoteConnectCancelPrompt",
    "XUserPlatformSpopPromptSetEventHandlers",
    "XUserPlatformSpopPromptComplete",
  }},
  {"IXUserImpl6", {
    "XUserIsSignOutPresent",
    "XUserSignOutAsync",
    "XUserSignOutResult",
  }},
  {"IXUserDeviceImpl", {
    "XUserFindForDevice",
    "XUserRegisterForDeviceAssociationChanged",
    "XUserUnregisterForDeviceAssociationChanged",
    "XUserGetDefaultAudioEndpointUtf16",
    "XUserRegisterForDefaultAudioEndpointUtf16Changed",
    "XUserUnregisterForDefaultAudioEndpointUtf16Changed",
    "XUserFindControllerForUserWithUiAsync",
    "XUserFindControllerForUserWithUiResult",
  }},
  {"IXUserGamertagImpl", {
    "XUserGetGamertag",
  }},
};

static void Check(bool ok, const char* what) {
  std::printf("%s %s\n", ok ? "PASS" : "FAIL", what);
  if (!ok) ++g_failures;
}

int main(int argc, char** argv) {
  if (argc > 2) {
    std::printf("FAIL usage: test_surface [table.json]\n");
    return 1;
  }
  const char* path = argc == 2 ? argv[1] : "table.json";
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    std::printf("FAIL cannot read interface table: %s\n", path);
    return 1;
  }
  std::ostringstream text;
  text << file.rdbuf();
  g_table = text.str();

  size_t methods = 0;
  for (const auto& surface : kSurface) {
    for (const char* method : surface.methods) {
      std::string label = std::string(surface.iface) + "::" + method + " has a named slot";
      Check(TableSlot(surface.iface, method) >= 3, label.c_str());
      ++methods;
    }
  }
  Check(TableSlot("IXPackageImpl4", "XPackageGetKind") >= 3 &&
            TableSlot("IXPackageImpl4", "XPackageGetPackageKind") == -1,
        "XPackageGetPackageKind is named XPackageGetKind in the interface table");

  std::printf("%s: %zu methods, %d failure(s)\n", g_failures ? "FAILED" : "ALL PASSED", methods, g_failures);
  return g_failures ? 1 : 0;
}
