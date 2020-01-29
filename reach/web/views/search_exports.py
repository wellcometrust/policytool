import json
import csv
import tempfile

import falcon

from reach.web.views import search


class CSVExport:
    """Let you search for terms in publications fulltexts. Returns a json.

    Args:
        es: An elasticsearch connection
        es_index: The index to search on
        es_explain: A boolean to enable|disable elasticsearch's explain.

    """

    def __init__(self, es, es_index, es_explain):
        self.es = es
        self.es_index = es_index
        self.es_explain = es_explain

    def yield_es_items(self, params, total, size=25):

        params['page'] = 0
        params['size'] = size
        for i in range(0, int(total / size) + 1):

            # Query builder starts page count at 1
            params['page'] = i + 1
            status, response = search._search_es(
                self.es,
                self.es_index,
                params,
                self.es_explain,
            )

            yield response

    def on_get(self, req, resp):
        """Returns the result of a search on the elasticsearch cluster.

        Args:
            req: The request passed to this controller
            resp: The reponse object to be returned
        """

        if not req.params:
            resp.body = json.dumps({
                'status': 'error',
                'message': "The request doesn't contain any parameters"
            })
            resp.status = falcon.HTTP_400

        # Get total number of results
        params = req.params
        params['size'] = 1
        params['fields'] = self.search_fields

        status, response = search._search_es(
            self.es,
            self.es_index,
            params,
            self.es_explain,
        )

        if not status:
            raise falcon.HTTPError(
                "400",
                description="Something went wrong with the query."
                            " Return status is false."
            )

        total = response['hits']['total']['value']
        if total == 0:
            raise falcon.HTTPError(
                "404",
                description="No results found for this query"
            )

        headers, policy_headers = self.get_headers(response)
        csv_file = None
        es_items = self.yield_es_items(params, total)
        try:
            csv_file = tempfile.TemporaryFile(mode="w+")
            writer = csv.DictWriter(
                csv_file,
                fieldnames=headers + policy_headers
            )
            writer.writeheader()
            for r in es_items:
                for item in self.yield_rows(headers, policy_headers, r):
                    writer.writerow(item)

            csv_file.seek(0)

            resp.content_type = 'text/csv'
            resp.append_header(
                'Content-Disposition',
                'attachment; filename="{filename}.csv"'.format(
                    filename='reach_export'
                )
            )
            # Falcon will call resp.stream.close()
            resp.stream = csv_file
        except Exception as e:  # noqa
            raise(e)
            if csv_file is not None:
                csv_file.close()

            else:
                resp.body = json.dumps({
                    'status': 'error',
                    'message': response
                })


class CitationsCSVExport(CSVExport):

    def __init__(self, es, es_index, es_explain):
        self.search_fields = ','.join([
            'match_title',
            'policies.title',
            'policies.organisation',
            'match_source',
            'match_publication',
            'match_authors'
        ])

        super(CitationsCSVExport, self).__init__(es, es_index, es_explain)

    def get_headers(self, response):
        doc = response['hits']['hits'][0]['_source']['doc']
        policy_headers = []

        if not len(doc['policies']):
            return doc.keys()[:-1], []

        for key in doc['policies'][0].keys():
            policy_headers.append('policies.{key_name}'.format(key_name=key))

        return list(doc.keys())[:-1], policy_headers

    def yield_rows(self, headers, policy_headers, data):
        for item in data['hits']['hits']:
            for policy in item['_source']['doc']['policies']:
                row = {}
                for key in headers:
                    row[key] = item['_source']['doc'][key]
                for key in policy_headers:
                    row[key] = policy[key.replace(
                        'policies.', ''
                    )]

                yield row


class PolicyDocsCSVExport(CSVExport):

    def __init__(self, es, es_index, es_explain):
        self.search_fields = ','.join([
            'title',
            'text',
            'organisation',
            'authors',
        ])

        super(PolicyDocsCSVExport, self).__init__(es, es_index, es_explain)

    def get_headers(self, response):
        return list(response['hits']['hits'][0]['_source']['doc'].keys()), []

    def yield_rows(self, headers, policy_headers, data):
        for item in data['hits']['hits']:
            yield item['_source']['doc']
