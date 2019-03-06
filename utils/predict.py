import pandas as pd
from functools import partial
from settings import settings

logger = settings.logger


def split_reference(reference):
    """Split up one individual reference into reference components.
    Each component is numbered by the reference it came from.
    """
    components = []

    # I need to divide each reference by the full stops
    # AND commas and categorise
    reference_sentences_mid = [
        elem.strip()
        for elem in reference.replace(
            ',', '.'
        ).replace(
            '?', '?.'
        ).replace(
            '!', '!.'
        ).split(".")
    ]

    for ref in reference_sentences_mid:
        if ref:
            components.append(ref)

    return components


def process_references(references):
    raw_reference_components = []
    for reference in references:
        # Get the components for this reference and store
        components = split_reference(reference['Reference'])

        for component in components:
            raw_reference_components.append({
                'Reference component': component,
                'Reference id': reference['Reference id'],
                'Document uri': reference['Document uri'],
                'Document id': reference['Document id']
            })

    reference_components = pd.DataFrame(raw_reference_components)

    logger.info("Reference components found")
    return reference_components


def decide_components(single_reference):
    """With the predicted components of one reference, decide which of
    these should be used for each component i.e. if there are multiple
    authors predicted and they arent next to each other, then decide which
    one to use.
    """

    # Add a block number, this groups neighbouring predictions of
    # the same type together.
    block_number = pd.DataFrame({
        'Block': (
            single_reference[
                "Predicted Category"
            ].shift(1) != single_reference[
                "Predicted Category"
            ]).astype(int).cumsum()
    })
    single_reference = pd.concat([single_reference, block_number], axis=1)
    single_reference_components = {}

    categories =  settings.REF_CLASSES
    for category in categories:

        # Are there any sentences of this type (i.e. Authors, Title)?
        classornot = sum(single_reference['Predicted Category'] == category)

        if classornot != 0:

            # Find how many blocks there are of this class type
            number_blocks = len(
                single_reference['Block'][single_reference[
                    'Predicted Category'
                ] == category].unique()
            )

            if number_blocks == 1:
                # Just record this block separated by commas
                single_reference_components.update({
                    category: ", ".join(
                        single_reference[
                            'Reference component'
                        ][single_reference[
                            'Predicted Category'
                        ] == category]
                    )
                })
            else:
                # Pick the block containing the highest probability
                # argmax takes the first argument anyway (so if there are 2
                # of the same probabilities it takes the first one)
                # could decide to do this randomly with argmax.choice()
                # (random choice)
                
                highest_probability_index = single_reference[
                    single_reference['Predicted Category'] == category
                ]['Prediction Probability'].idxmax()

                highest_probability_block = single_reference[
                    'Block'
                ][highest_probability_index]

                # Use everything in this block, separated by comma
                single_reference_components.update({
                    category: ", ".join(
                        single_reference[
                            "Reference component"
                        ][single_reference[
                            'Block'
                        ] == highest_probability_block]
                    )
                })
        else:
            # There are none of this classification, append with blank
            single_reference_components.update({category: ""})

    return single_reference_components


def single_reference_structure(components_single_reference,
                               prediction_probability_threshold):
    """Predict the structure for a single reference given all
    the components predicted for it.
    """
    # Delete all the rows which have a probability <0.75
    components_single_reference = components_single_reference[
        components_single_reference[
            'Prediction Probability'
        ].astype(float) > prediction_probability_threshold
    ]

    # Decide the best options for each reference component, resulting
    # in one structured reference
    single_reference = pd.DataFrame(
        decide_components(components_single_reference),
        index=[0]
    )

    return single_reference


def _get_structure(components_single_reference):
    # The components and predictions for one document one reference

    # Structure:
    single_reference = single_reference_structure(
        components_single_reference,
        settings.PREDICTION_PROBABILITY_THRESHOLD
    )

    if len(single_reference) != 0:

        # Only if there were some enteries for this reference with
        # high prediction probabilies
        single_reference[
            "Document id"
        ] = components_single_reference['Document id'].iloc[0]

        single_reference[
            "Reference id"
        ] = components_single_reference['Reference id'].iloc[0]

        single_reference[
            "Document uri"
        ] = components_single_reference['Document uri'].iloc[0]

    return pd.DataFrame.from_dict(single_reference)


def predict_structure(pool_map, reference_components_predictions,
                      prediction_probability_threshold):
    """
    Predict the structured references for all the references of
    one document.
    """

    # Convert to pd dataframe, although when this function is refactored we shouldnt have to do this
    reference_components_predictions = pd.DataFrame.from_dict(reference_components_predictions)

    document_components_list = [
        reference_components_predictions.loc[
            reference_components_predictions['Reference id'] == reference_id
        ]
        for reference_id in reference_components_predictions['Reference id'].unique()
    ]

    doc_references = pool_map(
        _get_structure,
        document_components_list
    )

    logger.info("[+] Reference structure predicted")
    return pd.concat(doc_references)


def predict_reference_comp(model, word_list):
    # To test what individual things predict,
    # it can deal with a list input or not
    # The maximum probability found is the probability
    # of the predicted classification

    predict_component = model.predict(word_list)
    predict_component_probas = model.predict_proba(word_list)
    predict_component_proba = [
        single_predict.max() for single_predict in predict_component_probas
    ]

    return predict_component[0], predict_component_proba[0]

def is_year(component):
    valid_years_range = range(1800, 2020)
    return (
                (
                    component.isdecimal()
                    and int(component) in valid_years_range
                )
                or
                (
                    len(component) == 6
                    and component[1:5].isdecimal()
                    and int(component[1:5]) in valid_years_range
                )
            )
        

def _get_component(component, model):

    if is_year(component):
        pred_cat = 'PubYear'
        pred_prob = 1
    else:
        pred_cat, pred_prob = predict_reference_comp(
            model,
            [component]
        )

    return {
            'Predicted Category': pred_cat,
            'Prediction Probability': pred_prob
            }

def predict_references(pool_map, model,
                       reference_components):

    """
    Predicts the categories for a list of reference components.
    Input:
    - pool_map: Pool map used for multiprocessing the predicting
    - model: The trained multinomial naive Bayes model for predicting the categories of reference components
    - reference_components: A list of reference components
    Output:
    - A list of dicts [{"Predicted Category": , "Prediction Probability": } ...]
    """

    logger.info(
        "[+] Predicting the categories of %s  reference components ...",
        str(len(reference_components))
    )
    predict_all = []

    # The model cant deal with predicting so many all at once,
    # so predict in a loop

    predict_all = list(pool_map(
        partial(_get_component,
                model=model),
        reference_components
    ))

    logger.info("Predictions complete")

    return predict_all

