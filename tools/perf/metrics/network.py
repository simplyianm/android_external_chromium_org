# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import base64
import gzip
import hashlib
import io
import logging
import zlib

from metrics import Metric
from telemetry.page import page_measurement
# All network metrics are Chrome only for now.
from telemetry.core.backends.chrome import inspector_network
from telemetry.timeline import recording_options


class NetworkMetricException(page_measurement.MeasurementFailure):
  pass


class HTTPResponse(object):
  """ Represents an HTTP response from a timeline event."""
  def __init__(self, event):
    self._response = (
        inspector_network.InspectorNetworkResponseData.FromTimelineEvent(event))
    self._content_length = None

  @property
  def response(self):
    return self._response

  @property
  def url_signature(self):
    return hashlib.md5(self.response.url).hexdigest()

  @property
  def content_length(self):
    if self._content_length is None:
      self._content_length = self.GetContentLength()
    return self._content_length

  @property
  def has_original_content_length(self):
    return 'X-Original-Content-Length' in self.response.headers

  @property
  def original_content_length(self):
    if self.has_original_content_length:
      return int(self.response.GetHeader('X-Original-Content-Length'))
    return 0

  @property
  def data_saving_rate(self):
    if (self.response.served_from_cache or
        not self.has_original_content_length or
        self.original_content_length <= 0):
      return 0.0
    return (float(self.original_content_length - self.content_length) /
            self.original_content_length)

  def GetContentLengthFromBody(self):
    resp = self.response
    body, base64_encoded = resp.GetBody()
    if not body:
      return 0
    # The binary data like images, etc is base64_encoded. Decode it to get
    # the actualy content length.
    if base64_encoded:
      decoded = base64.b64decode(body)
      return len(decoded)

    encoding = resp.GetHeader('Content-Encoding')
    if not encoding:
      return len(body)
    # The response body returned from a timeline event is always decompressed.
    # So, we need to compress it to get the actual content length if headers
    # say so.
    encoding = encoding.lower()
    if encoding == 'gzip':
      return self.GetGizppedBodyLength(body)
    elif encoding == 'deflate':
      return len(zlib.compress(body, 9))
    else:
      raise NetworkMetricException, (
          'Unknown Content-Encoding %s for %s' % (encoding, resp.url))

  def GetContentLength(self):
    cl = 0
    try:
      cl = self.GetContentLengthFromBody()
    except Exception, e:
      resp = self.response
      logging.warning('Fail to get content length for %s from body: %s',
                      resp.url[:100], e)
      cl_header = resp.GetHeader('Content-Length')
      if cl_header:
        cl = int(cl_header)
      else:
        body, _ = resp.GetBody()
        if body:
          cl = len(body)
    return cl

  @staticmethod
  def GetGizppedBodyLength(body):
    if not body:
      return 0
    bio = io.BytesIO()
    try:
      with gzip.GzipFile(fileobj=bio, mode="wb", compresslevel=9) as f:
        f.write(body.encode('utf-8'))
    except Exception, e:
      logging.warning('Fail to gzip response body: %s', e)
      raise e
    return len(bio.getvalue())


class NetworkMetric(Metric):
  """A network metric based on timeline events."""

  def __init__(self):
    super(NetworkMetric, self).__init__()

    # Whether to add detailed result for each sub-resource in a page.
    self.add_result_for_resource = False
    self.compute_data_saving = False
    self._events = None

  def Start(self, page, tab):
    self._events = None
    opts = recording_options.TimelineRecordingOptions()
    opts.record_network = True
    tab.StartTimelineRecording(opts)

  def Stop(self, page, tab):
    assert self._events is None
    tab.StopTimelineRecording()

  def IterResponses(self, tab):
    if self._events is None:
      self._events = tab.timeline_model.GetAllEventsOfName('HTTPResponse')
    if len(self._events) == 0:
      return
    for e in self._events:
      yield self.ResponseFromEvent(e)

  def ResponseFromEvent(self, event):
    return HTTPResponse(event)

  def AddResults(self, tab, results):
    content_length = 0
    original_content_length = 0

    for resp in self.IterResponses(tab):
      # Ignore content length calculation for cache hit.
      if resp.response.served_from_cache:
        continue

      resource = resp.response.url
      resource_signature = resp.url_signature
      cl = resp.content_length
      if resp.has_original_content_length:
        ocl = resp.original_content_length
        if ocl < cl:
          logging.warning('original content length (%d) is less than content '
                        'lenght(%d) for resource %s', ocl, cl, resource)
        if self.add_result_for_resource:
          results.Add('resource_data_saving_' + resource_signature,
                      'percent', resp.data_saving_rate * 100)
          results.Add('resource_original_content_length_' + resource_signature,
                      'bytes', ocl)
        original_content_length += ocl
      else:
        original_content_length += cl
      if self.add_result_for_resource:
        results.Add(
            'resource_content_length_' + resource_signature, 'bytes', cl)
      content_length += cl

    results.Add('content_length', 'bytes', content_length)
    results.Add('original_content_length', 'bytes', original_content_length)
    if self.compute_data_saving:
      if (original_content_length > 0 and
          original_content_length >= content_length):
        saving = (float(original_content_length-content_length) * 100 /
                  original_content_length)
        results.Add('data_saving', 'percent', saving)
      else:
        results.Add('data_saving', 'percent', 0.0)
